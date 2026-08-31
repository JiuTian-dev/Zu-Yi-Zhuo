"""Provider protocol kept independent from any model vendor SDK."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel


class LLMProvider(Protocol):
    """Minimal async contract used by Observer/Router/Host adapters.

    Implementations may return a Pydantic model, a mapping, or JSON text from
    ``structured``. The resilient adapter validates all three forms at the
    boundary so downstream orchestration only sees typed contracts.
    """

    async def structured(
        self,
        task: str,
        messages: Sequence[Mapping[str, str]],
        schema: type[BaseModel],
        config: Mapping[str, Any] | None = None,
    ) -> Any: ...

    async def text(
        self,
        task: str,
        messages: Sequence[Mapping[str, str]],
        config: Mapping[str, Any] | None = None,
    ) -> str: ...
