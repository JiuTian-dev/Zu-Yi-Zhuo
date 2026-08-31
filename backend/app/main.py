"""Deployment entrypoint for the conversation orchestrator API.

Run from ``backend/`` with ``uvicorn app.main:app``. Set
``TABLE_REPOSITORY_PATH`` to opt into the atomic JSON repository; leaving it
unset keeps the lightweight in-memory mode used by tests and local demos.
``CONVERSATION_PROVIDER`` defaults to ``deterministic``; ``openai`` opts into
the optional OpenAI Responses adapter.
"""

import os

from app.api.app import create_app
from app.api.repository import JsonTableRepository
from app.providers import OpenAIResponsesProvider, ProviderConfigurationError


def _build_provider():
    mode = os.environ.get("CONVERSATION_PROVIDER", "deterministic").strip().lower()
    if mode in {"", "deterministic"}:
        return None
    if mode == "openai":
        try:
            return OpenAIResponsesProvider()
        except ProviderConfigurationError as error:
            raise RuntimeError(f"CONVERSATION_PROVIDER=openai is not configured: {error}") from error
    raise RuntimeError(
        "CONVERSATION_PROVIDER must be one of: deterministic, openai"
    )


def _build_app():
    path = os.environ.get("TABLE_REPOSITORY_PATH", "").strip()
    repository = JsonTableRepository(path) if path else None
    return create_app(repository, _build_provider())


app = _build_app()

__all__ = ("app",)
