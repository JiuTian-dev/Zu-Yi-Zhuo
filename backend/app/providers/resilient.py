"""Fail-closed provider calls for model-backed orchestration steps."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .base import LLMProvider

ModelT = TypeVar("ModelT", bound=BaseModel)


class ProviderCallError(RuntimeError):
    """Raised when a structured call has no safe typed fallback."""


@dataclass(frozen=True)
class StructuredCall(Generic[ModelT]):
    """Typed result plus enough metadata for observability and replay."""

    value: ModelT
    attempts: int
    used_fallback: bool
    error: str | None = None


@dataclass(frozen=True)
class TextCall:
    """Host text result; ``value=None`` means no event should be emitted."""

    value: str | None
    attempts: int
    used_fallback: bool
    error: str | None = None


def _parse_structured(raw: Any, schema: type[ModelT]) -> ModelT:
    if isinstance(raw, schema):
        return raw
    if isinstance(raw, (str, bytes, bytearray)):
        return schema.model_validate_json(raw)
    return schema.model_validate(raw)


def _error_text(error: Exception) -> str:
    message = str(error).strip()
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


async def call_structured(
    provider: LLMProvider,
    *,
    task: str,
    messages: Sequence[Mapping[str, str]],
    schema: type[ModelT],
    previous: ModelT | None = None,
    fallback_factory: Callable[[], ModelT] | None = None,
    config: Mapping[str, Any] | None = None,
) -> StructuredCall[ModelT]:
    """Call structured output at most twice, then fail closed.

    A malformed response or provider exception gets exactly one repair retry.
    If that also fails, the previous typed value is preferred; otherwise an
    explicit fallback factory is required. This prevents partial model output
    from crossing into state mutation or a Host event.
    """

    last_error: Exception | None = None
    for attempt in (1, 2):
        call_config = dict(config or {})
        if attempt == 2:
            call_config.update({"retry": True, "attempt": attempt})
        try:
            raw = await provider.structured(task, messages, schema, call_config)
            value = _parse_structured(raw, schema)
            return StructuredCall(value=value, attempts=attempt, used_fallback=False)
        except Exception as error:  # provider and parse errors both fail closed
            last_error = error

    if previous is not None:
        return StructuredCall(
            value=previous.model_copy(deep=True),
            attempts=2,
            used_fallback=True,
            error=_error_text(last_error) if last_error else "structured call failed",
        )
    if fallback_factory is not None:
        try:
            fallback = _parse_structured(fallback_factory(), schema)
        except Exception as error:
            raise ProviderCallError(f"invalid structured fallback: {_error_text(error)}") from error
        return StructuredCall(value=fallback, attempts=2, used_fallback=True,
                              error=_error_text(last_error) if last_error else "structured call failed")
    raise ProviderCallError(_error_text(last_error) if last_error else "structured call failed")


async def call_text(
    provider: LLMProvider,
    *,
    task: str,
    messages: Sequence[Mapping[str, str]],
    fallback_text: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> TextCall:
    """Call Host text at most twice; empty or failed output is never emitted."""

    last_error: Exception | None = None
    for attempt in (1, 2):
        call_config = dict(config or {})
        if attempt == 2:
            call_config.update({"retry": True, "attempt": attempt})
        try:
            value = await provider.text(task, messages, call_config)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("provider returned empty host text")
            return TextCall(value=value.strip(), attempts=attempt, used_fallback=False)
        except Exception as error:  # no half-built Host event crosses this boundary
            last_error = error

    return TextCall(
        value=fallback_text.strip() if isinstance(fallback_text, str) and fallback_text.strip() else None,
        attempts=2,
        used_fallback=True,
        error=_error_text(last_error) if last_error else "text call failed",
    )
