"""Deployment entrypoint for the conversation orchestrator API.

Run from ``backend/`` with ``uvicorn app.main:app``. Set
``TABLE_REPOSITORY_PATH`` to opt into the atomic JSON repository; leaving it
unset keeps the lightweight in-memory mode used by tests and local demos.
``CONVERSATION_PROVIDER`` defaults to ``deterministic``; ``openai`` opts into
the optional OpenAI Responses adapter.
"""

import os
import json

from app.api.app import create_app
from app.api.repository import JsonTableRepository
from app.providers import OpenAIResponsesProvider, ProviderConfigurationError
from app.sources import CommandCandidateSource, CommandContentSignalSource, CommandPersonalContextSource


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


def _build_candidate_source():
    raw = os.environ.get("CANDIDATE_SOURCE_COMMAND", "").strip()
    if not raw:
        return None
    try:
        command = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("CANDIDATE_SOURCE_COMMAND must be a JSON string array") from error
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        raise RuntimeError("CANDIDATE_SOURCE_COMMAND must be a non-empty JSON string array")
    try:
        return CommandCandidateSource(command)
    except ValueError as error:
        raise RuntimeError(f"invalid CANDIDATE_SOURCE_COMMAND: {error}") from error


def _build_content_source():
    raw = os.environ.get("CONTENT_SIGNAL_SOURCE_COMMAND", "").strip()
    if not raw:
        return None
    try:
        command = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("CONTENT_SIGNAL_SOURCE_COMMAND must be a JSON string array") from error
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        raise RuntimeError("CONTENT_SIGNAL_SOURCE_COMMAND must be a non-empty JSON string array")
    try:
        return CommandContentSignalSource(command)
    except ValueError as error:
        raise RuntimeError(f"invalid CONTENT_SIGNAL_SOURCE_COMMAND: {error}") from error


def _build_personal_context_source():
    raw = os.environ.get("PERSONAL_CONTEXT_SOURCE_COMMAND", "").strip()
    if not raw:
        return None
    try:
        command = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("PERSONAL_CONTEXT_SOURCE_COMMAND must be a JSON string array") from error
    if not isinstance(command, list) or not command or any(not isinstance(item, str) for item in command):
        raise RuntimeError("PERSONAL_CONTEXT_SOURCE_COMMAND must be a non-empty JSON string array")
    try:
        return CommandPersonalContextSource(command)
    except ValueError as error:
        raise RuntimeError(f"invalid PERSONAL_CONTEXT_SOURCE_COMMAND: {error}") from error


def _build_source_match_preview_ttl() -> float:
    raw = os.environ.get("SOURCE_MATCH_PREVIEW_TTL_SECONDS", "300").strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError("SOURCE_MATCH_PREVIEW_TTL_SECONDS must be a positive number") from error
    if value <= 0:
        raise RuntimeError("SOURCE_MATCH_PREVIEW_TTL_SECONDS must be a positive number")
    return value


def _build_sync_window() -> float:
    raw = os.environ.get("SYNC_WINDOW_SECONDS", "1800").strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError("SYNC_WINDOW_SECONDS must be a positive number") from error
    if value <= 0:
        raise RuntimeError("SYNC_WINDOW_SECONDS must be a positive number")
    return value


def _build_app():
    path = os.environ.get("TABLE_REPOSITORY_PATH", "").strip()
    repository = JsonTableRepository(path) if path else None
    return create_app(
        repository,
        _build_provider(),
        _build_candidate_source(),
        content_source=_build_content_source(),
        personal_context_source=_build_personal_context_source(),
        source_match_preview_ttl_seconds=_build_source_match_preview_ttl(),
        sync_window_seconds=_build_sync_window(),
    )


app = _build_app()

__all__ = ("app",)
