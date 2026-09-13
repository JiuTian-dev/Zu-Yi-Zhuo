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


def _schema_fields(schema: type[BaseModel] | None) -> set[str]:
    fields: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            fields.update(value.get("properties", {}))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    if schema is not None:
        visit(schema.model_json_schema())
    return fields


def _error_text(error: Exception, schema: type[BaseModel] | None = None) -> str:
    # ValidationError and transport errors may embed raw inputs or credentials.
    # Only bounded schema locations and error codes may leave this boundary.
    if isinstance(error, ValidationError):
        defects = []
        allowed_fields = _schema_fields(schema)
        for item in error.errors(include_input=False, include_context=False, include_url=False)[:5]:
            location = ".".join(
                str(part) if isinstance(part, int) or part in allowed_fields else "field"
                for part in item["loc"][:6]
            ) or "response"
            defects.append(f"{location}: {item['type']}")
        return f"ValidationError: {'; '.join(defects)}"
    return type(error).__name__


def _repair_feedback(error: Exception | None, schema: type[BaseModel]) -> str:
    problem = _error_text(error, schema) if error is not None else "invalid response"
    return (
        f"The previous attempt did not satisfy the response contract ({problem}). "
        "Generate a fresh complete JSON object matching the provided schema. "
        "Use double quotes, include required fields, and include no markdown or extra fields. "
        "Preserve the evidence boundary; omit unsupported claims instead of inventing values."
    )


async def call_structured(
    provider: LLMProvider,
    *,
    task: str,
    messages: Sequence[Mapping[str, str]],
    schema: type[ModelT],
    previous: ModelT | None = None,
    fallback_factory: Callable[[], ModelT] | None = None,
    config: Mapping[str, Any] | None = None,
    max_attempts: int = 2,
) -> StructuredCall[ModelT]:
    """Call structured output at most twice, then fail closed.

    By default a malformed response or provider exception gets one repair retry.
    Bounded workers may disable that retry with max_attempts=1.
    If that also fails, the previous typed value is preferred; otherwise an
    explicit fallback factory is required. This prevents partial model output
    from crossing into state mutation or a Host event.
    """

    if max_attempts not in (1, 2):
        raise ValueError("max_attempts must be 1 or 2")
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        call_config = dict(config or {})
        call_messages = list(messages)
        if attempt == 2:
            call_config.update({"retry": True, "attempt": attempt})
            call_messages.append({"role": "system", "content": _repair_feedback(last_error, schema)})
        try:
            raw = await provider.structured(task, call_messages, schema, call_config)
            value = _parse_structured(raw, schema)
            return StructuredCall(value=value, attempts=attempt, used_fallback=False)
        except Exception as error:  # provider and parse errors both fail closed
            last_error = error

    if previous is not None:
        return StructuredCall(
            value=previous.model_copy(deep=True),
            attempts=max_attempts,
            used_fallback=True,
            error=_error_text(last_error, schema) if last_error else "structured call failed",
        )
    if fallback_factory is not None:
        try:
            fallback = _parse_structured(fallback_factory(), schema)
        except Exception as error:
            raise ProviderCallError(f"invalid structured fallback: {_error_text(error, schema)}") from error
        return StructuredCall(value=fallback, attempts=max_attempts, used_fallback=True,
                              error=_error_text(last_error, schema) if last_error else "structured call failed")
    raise ProviderCallError(_error_text(last_error, schema) if last_error else "structured call failed")


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
