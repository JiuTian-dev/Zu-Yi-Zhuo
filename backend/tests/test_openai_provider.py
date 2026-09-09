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


class _ChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("response_format"):
            content = '{"action":"PROBE"}'
        else:
            content = "  可继续追问预算验收。  "
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class _ChatClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_ChatCompletions())


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


def test_chat_text_maps_responses_options_to_chat_completions() -> None:
    client = _ChatClient()
    provider = OpenAIResponsesProvider(
        client, model="omen-alpha", api_style="chat"
    )

    result = asyncio.run(
        provider.text(
            "生成一句主持话",
            [{"role": "user", "content": "预算验收怎么做？"}],
            {"max_output_tokens": 32, "reasoning": {"effort": "low"}},
        )
    )

    assert result == "可继续追问预算验收。"
    call = client.chat.completions.calls[0]
    assert call["model"] == "omen-alpha"
    assert call["max_tokens"] == 32
    assert "reasoning" not in call
    assert call["messages"] == [
        {"role": "system", "content": "生成一句主持话"},
        {"role": "user", "content": "预算验收怎么做？"},
    ]


def test_chat_structured_validates_json_object() -> None:
    client = _ChatClient()
    provider = OpenAIResponsesProvider(client, model="omen-alpha", api_style="chat")

    result = asyncio.run(
        provider.structured("请判断下一步动作", [], _Decision)
    )

    assert result.action == "PROBE"
    call = client.chat.completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][0]["role"] == "system"
    assert "action" in call["messages"][0]["content"]
