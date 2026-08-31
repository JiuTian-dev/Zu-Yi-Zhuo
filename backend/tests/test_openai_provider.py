import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.providers import OpenAIResponsesProvider, ProviderConfigurationError


class _Decision(BaseModel):
    action: str


class _Responses:
    def __init__(self) -> None:
        self.parse_calls: list[dict] = []
        self.create_calls: list[dict] = []

    async def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return SimpleNamespace(output_parsed=_Decision(action="PROBE"))

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(output_text="  可继续追问预算验收。  ")


class _Client:
    def __init__(self) -> None:
        self.responses = _Responses()


def test_structured_uses_responses_parse_and_preserves_messages() -> None:
    client = _Client()
    provider = OpenAIResponsesProvider(client, model="demo-model")

    result = asyncio.run(
        provider.structured(
            "请判断下一步动作",
            [{"role": "user", "content": "预算验收怎么做？"}, {"role": "assistant", "content": ""}],
            _Decision,
            {"temperature": 0, "retry": True, "unknown": "ignored"},
        )
    )

    assert result.action == "PROBE"
    call = client.responses.parse_calls[0]
    assert call["model"] == "demo-model"
    assert call["text_format"] is _Decision
    assert call["instructions"] == "请判断下一步动作"
    assert call["input"] == [{"role": "user", "content": "预算验收怎么做？"}]
    assert "retry" not in call and "unknown" not in call


def test_text_uses_responses_create_and_returns_trimmed_text() -> None:
    client = _Client()
    provider = OpenAIResponsesProvider(client, model="demo-model")

    result = asyncio.run(provider.text("生成一句主持话", [], {"max_output_tokens": 32}))

    assert result == "可继续追问预算验收。"
    assert client.responses.create_calls[0]["max_output_tokens"] == 32


def test_missing_key_is_explicit_when_constructing_default_client(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        OpenAIResponsesProvider()
