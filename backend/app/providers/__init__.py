"""Provider contracts and fail-closed execution helpers."""

from .base import LLMProvider
from .resilient import (
    ProviderCallError,
    StructuredCall,
    TextCall,
    call_structured,
    call_text,
)

__all__ = (
    "LLMProvider",
    "ProviderCallError",
    "StructuredCall",
    "TextCall",
    "call_structured",
    "call_text",
)
