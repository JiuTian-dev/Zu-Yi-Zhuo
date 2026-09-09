"""Optional OpenAI Responses API adapter.

The core application deliberately depends only on :class:`LLMProvider`.  This
module is an opt-in integration for deployments that install the OpenAI SDK
and provide ``OPENAI_API_KEY``.  Importing ``app.providers`` does not import
the vendor SDK, so deterministic demo mode remains dependency-free.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
import json
from typing import Any
from uuid import uuid4

from pydantic import BaseModel


class ProviderConfigurationError(RuntimeError):
    """Raised when the optional provider cannot be configured safely."""


def _input_messages(
    task: str, messages: Sequence[Mapping[str, str]]
) -> tuple[str, list[dict[str, str]]]:
    instruction = task.strip()
    if not instruction:
        raise ValueError("provider task must be non-empty")
    normalized: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user")).strip() or "user"
        content = str(message.get("content", ""))
        if not content.strip():
            continue
        normalized.append({"role": role, "content": content})
    return instruction, normalized


def _request_options(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep retry bookkeeping and unknown config keys out of the SDK call."""

    source = config or {}
    allowed = (
        "model",
        "temperature",
        "max_output_tokens",
        "top_p",
        "reasoning",
        "store",
        "metadata",
        "verbosity",
        "previous_response_id",
        "truncation",
        "timeout",
    )
    return {key: source[key] for key in allowed if key in source}


class OpenAIResponsesProvider:
    """Async provider backed by OpenAI Responses or Chat Completions.

    ``client`` is injectable for tests and for callers that already manage an
    SDK client. With no client, the SDK is imported lazily and configured from
    ``OPENAI_API_KEY``, ``OPENAI_BASE_URL`` and ``OPENAI_MODEL``. OpenAI-compatible
    Chat Completions providers are selected with ``OPENAI_API_STYLE=chat``.
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        api_style: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model = (model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
        if not self.model:
            raise ProviderConfigurationError("OPENAI_MODEL must be non-empty")
        self._default_timeout = timeout
        endpoint = (base_url or os.getenv("OPENAI_BASE_URL") or "").strip()
        self._is_opencode_go = "opencode.ai/zen/go" in endpoint.lower()
        selected_style = (api_style or os.getenv("OPENAI_API_STYLE") or "").strip().lower()
        if not selected_style:
            selected_style = "chat" if self._is_opencode_go else "responses"
        if selected_style not in {"responses", "chat"}:
            raise ProviderConfigurationError("OPENAI_API_STYLE must be responses or chat")
        self.api_style = selected_style
        if client is not None:
            self._client = client
            return

        token = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        if not token:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required when no client is supplied"
            )
        try:
            from openai import AsyncOpenAI
        except ImportError as error:  # pragma: no cover - exercised without optional extra
            raise ProviderConfigurationError(
                "install the optional 'openai' dependency to use this provider"
            ) from error

        options: dict[str, Any] = {"api_key": token}
        if endpoint:
            options["base_url"] = endpoint
        if self.api_style == "chat" and self._is_opencode_go:
            options["default_headers"] = {
                "User-Agent": "zuo-yi-zhuo/0.1",
                "x-opencode-session": os.getenv("OPENCODE_SESSION_ID") or uuid4().hex,
            }
        if timeout is not None:
            options["timeout"] = timeout
        self._client = AsyncOpenAI(**options)

    def _options(self, config: Mapping[str, Any] | None) -> dict[str, Any]:
        options = _request_options(config)
        options.setdefault("model", self.model)
        if self._default_timeout is not None:
            options.setdefault("timeout", self._default_timeout)
        return options

    def _chat_options(self, config: Mapping[str, Any] | None) -> dict[str, Any]:
        options = self._options(config)
        max_output_tokens = options.pop("max_output_tokens", None)
        if max_output_tokens is not None:
            options["max_tokens"] = max_output_tokens
        for key in ("reasoning", "store", "metadata", "verbosity", "previous_response_id", "truncation"):
            options.pop(key, None)
        return options

    @staticmethod
    def _chat_messages(instruction: str, input_messages: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
        return [{"role": "system", "content": instruction}, *input_messages]

    @staticmethod
    def _chat_text(response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        message = getattr(choices[0], "message", None) if choices else None
        value = getattr(message, "content", None)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("OpenAI Chat Completions returned empty text")
        return value.strip()

    async def structured(
        self,
        task: str,
        messages: Sequence[Mapping[str, str]],
        schema: type[BaseModel],
        config: Mapping[str, Any] | None = None,
    ) -> Any:
        """Return the SDK's parsed Pydantic value for a structured task."""

        instruction, input_messages = _input_messages(task, messages)
        if self.api_style == "chat":
            create = getattr(getattr(self._client, "chat", None), "completions", None)
            create = getattr(create, "create", None)
            if create is None:
                raise ProviderConfigurationError(
                    "the configured OpenAI SDK client does not expose chat.completions.create"
                )
            schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
            response = await create(
                messages=self._chat_messages(
                    f"{instruction}\nReturn only valid JSON matching this schema: {schema_json}",
                    input_messages,
                ),
                response_format={"type": "json_object"},
                **self._chat_options(config),
            )
            raw = self._chat_text(response).removeprefix("```json").removesuffix("```").strip()
            return schema.model_validate(json.loads(raw))
        parse = getattr(getattr(self._client, "responses", None), "parse", None)
        if parse is None:
            raise ProviderConfigurationError(
                "the configured OpenAI SDK client does not expose responses.parse"
            )
        response = await parse(
            instructions=instruction,
            input=input_messages,
            text_format=schema,
            **self._options(config),
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ValueError("OpenAI Responses returned no parsed structured output")
        return parsed

    async def text(
        self,
        task: str,
        messages: Sequence[Mapping[str, str]],
        config: Mapping[str, Any] | None = None,
    ) -> str:
        """Return non-empty assistant text; empty responses fail closed."""

        instruction, input_messages = _input_messages(task, messages)
        if self.api_style == "chat":
            create = getattr(getattr(self._client, "chat", None), "completions", None)
            create = getattr(create, "create", None)
            if create is None:
                raise ProviderConfigurationError(
                    "the configured OpenAI SDK client does not expose chat.completions.create"
                )
            response = await create(
                messages=self._chat_messages(instruction, input_messages),
                **self._chat_options(config),
            )
            return self._chat_text(response)
        create = getattr(getattr(self._client, "responses", None), "create", None)
        if create is None:
            raise ProviderConfigurationError(
                "the configured OpenAI SDK client does not expose responses.create"
            )
        response = await create(
            instructions=instruction,
            input=input_messages,
            **self._options(config),
        )
        value = getattr(response, "output_text", None)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("OpenAI Responses returned empty text")
        return value.strip()


__all__ = ("OpenAIResponsesProvider", "ProviderConfigurationError")
