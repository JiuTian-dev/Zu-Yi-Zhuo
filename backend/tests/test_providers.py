import asyncio
import pytest
from pydantic import BaseModel

from app.providers import ProviderCallError, call_structured, call_text


class _Decision(BaseModel):
    action: str


class _FakeProvider:
    def __init__(self, structured_values=None, text_values=None):
        self.structured_values = list(structured_values or [])
        self.text_values = list(text_values or [])
        self.structured_configs = []
        self.structured_messages = []
        self.text_configs = []

    async def structured(self, task, messages, schema, config=None):
        self.structured_configs.append(dict(config or {}))
        self.structured_messages.append(list(messages))
        value = self.structured_values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    async def text(self, task, messages, config=None):
        self.text_configs.append(dict(config or {}))
        value = self.text_values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_structured_output_is_validated_and_returns_typed_value() -> None:
    provider = _FakeProvider(structured_values=['{"action":"PROBE"}'])
    result = asyncio.run(call_structured(
        provider, task="route", messages=[], schema=_Decision, config={"model": "demo"}
    ))
    assert result.value.action == "PROBE"
    assert (result.attempts, result.used_fallback) == (1, False)
    assert provider.structured_configs == [{"model": "demo"}]


def test_structured_parse_failure_gets_exactly_one_retry() -> None:
    provider = _FakeProvider(structured_values=["not-json", {"action": "REFRAME"}])
    result = asyncio.run(call_structured(provider, task="route", messages=[], schema=_Decision))
    assert result.value.action == "REFRAME"
    assert result.attempts == 2
    assert provider.structured_configs[1] == {"retry": True, "attempt": 2}
    assert "json_invalid" in provider.structured_messages[1][-1]["content"]
    assert "not-json" not in provider.structured_messages[1][-1]["content"]


def test_structured_retry_explains_schema_defect_without_echoing_input() -> None:
    secret = "private-input-do-not-repeat"
    provider = _FakeProvider(structured_values=[{"action": {"key": secret}}, {"action": "PASS"}])
    result = asyncio.run(call_structured(provider, task="route", messages=[], schema=_Decision))
    assert not result.used_fallback
    repair = provider.structured_messages[1][-1]["content"]
    assert "action: string_type" in repair
    assert secret not in repair


def test_structured_one_attempt_bounds_work_and_redacts_provider_errors() -> None:
    provider = _FakeProvider(structured_values=[ValueError("secret-api-key")])
    result = asyncio.run(call_structured(
        provider, task="route", messages=[], schema=_Decision, max_attempts=1,
        fallback_factory=lambda: _Decision(action="SILENCE"),
    ))
    assert result.attempts == 1 and result.used_fallback
    assert result.error == "ValueError"
    assert len(provider.structured_configs) == 1


def test_structured_failure_reuses_previous_typed_value() -> None:
    previous = _Decision(action="SILENCE")
    provider = _FakeProvider(structured_values=[ValueError("upstream"), {"missing": "action"}])
    result = asyncio.run(call_structured(provider, task="route", messages=[], schema=_Decision, previous=previous))
    assert result.value == previous
    assert result.used_fallback and result.attempts == 2
    assert "ValidationError" in (result.error or "")
    result.value.action = "PROBE"
    assert previous.action == "SILENCE"


def test_structured_failure_uses_explicit_fallback_or_raises() -> None:
    provider = _FakeProvider(structured_values=[ValueError("first"), ValueError("second")])
    result = asyncio.run(call_structured(
        provider, task="route", messages=[], schema=_Decision,
        fallback_factory=lambda: _Decision(action="SILENCE"),
    ))
    assert result.value.action == "SILENCE" and result.used_fallback

    provider = _FakeProvider(structured_values=[ValueError("first"), ValueError("second")])
    with pytest.raises(ProviderCallError, match="ValueError"):
        asyncio.run(call_structured(provider, task="route", messages=[], schema=_Decision))


def test_text_failure_never_emits_half_built_host_event() -> None:
    provider = _FakeProvider(text_values=["", ValueError("timeout")])
    result = asyncio.run(call_text(provider, task="host", messages=[]))
    assert result.value is None and result.used_fallback and result.attempts == 2

    provider = _FakeProvider(text_values=[ValueError("timeout"), "  可继续追问预算验收。  "])
    result = asyncio.run(call_text(provider, task="host", messages=[]))
    assert result.value == "可继续追问预算验收。" and result.attempts == 2
