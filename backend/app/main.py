"""Deployment entrypoint for the conversation orchestrator API.

Run from ``backend/`` with ``uvicorn app.main:app``. Set
``TABLE_REPOSITORY_PATH`` to opt into the atomic JSON repository; leaving it
unset keeps the lightweight in-memory mode used by tests and local demos.
``CONVERSATION_PROVIDER`` defaults to ``deterministic``; ``openai`` opts into
the optional OpenAI Responses adapter.  Set ``TABLE_REPOSITORY_PATH`` for a
restart-safe shared JSON repository; ``SHARED_EPHEMERAL_STORE_PATH``,
``SHARED_RATE_LIMIT_PATH`` and ``EVENT_BUS_PATH`` opt into SQLite coordination
for multi-worker deployments.  ``*_SOURCE_URL`` + ``*_SOURCE_TOKEN`` configure
server-side HTTPS/OAuth gateways when command wrappers are not used.
"""

import os
import json

from app.api.app import create_app
from app.api.repository import JsonTableRepository
from app.api.event_bus import SQLiteEventBus
from app.auth.zhihu import build_zhihu_oauth_service
from app.providers import OpenAIResponsesProvider, ProviderConfigurationError
from app.sources import (
    CommandCandidateSource,
    CommandContentSignalSource,
    CommandPersonalContextSource,
    HttpCandidateSource,
    HttpContentSignalSource,
    HttpPersonalContextSource,
)


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
    if raw:
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
    endpoint = os.environ.get("CANDIDATE_SOURCE_URL", "").strip()
    if not endpoint:
        if os.environ.get("CANDIDATE_SOURCE_TOKEN", "").strip():
            raise RuntimeError("CANDIDATE_SOURCE_TOKEN requires CANDIDATE_SOURCE_URL")
        return None
    try:
        return HttpCandidateSource(
            endpoint,
            token=os.environ.get("CANDIDATE_SOURCE_TOKEN"),
            allow_insecure_http=_allow_insecure_source_http(),
        )
    except ValueError as error:
        raise RuntimeError(f"invalid CANDIDATE_SOURCE_URL: {error}") from error


def _build_content_source():
    raw = os.environ.get("CONTENT_SIGNAL_SOURCE_COMMAND", "").strip()
    if raw:
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
    endpoint = os.environ.get("CONTENT_SIGNAL_SOURCE_URL", "").strip()
    if not endpoint:
        if os.environ.get("CONTENT_SIGNAL_SOURCE_TOKEN", "").strip():
            raise RuntimeError("CONTENT_SIGNAL_SOURCE_TOKEN requires CONTENT_SIGNAL_SOURCE_URL")
        return None
    try:
        return HttpContentSignalSource(
            endpoint,
            token=os.environ.get("CONTENT_SIGNAL_SOURCE_TOKEN"),
            allow_insecure_http=_allow_insecure_source_http(),
        )
    except ValueError as error:
        raise RuntimeError(f"invalid CONTENT_SIGNAL_SOURCE_URL: {error}") from error


def _build_personal_context_source():
    raw = os.environ.get("PERSONAL_CONTEXT_SOURCE_COMMAND", "").strip()
    if raw:
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
    endpoint = os.environ.get("PERSONAL_CONTEXT_SOURCE_URL", "").strip()
    if not endpoint:
        if os.environ.get("PERSONAL_CONTEXT_SOURCE_TOKEN", "").strip():
            raise RuntimeError("PERSONAL_CONTEXT_SOURCE_TOKEN requires PERSONAL_CONTEXT_SOURCE_URL")
        return None
    try:
        return HttpPersonalContextSource(
            endpoint,
            token=os.environ.get("PERSONAL_CONTEXT_SOURCE_TOKEN"),
            allow_insecure_http=_allow_insecure_source_http(),
        )
    except ValueError as error:
        raise RuntimeError(f"invalid PERSONAL_CONTEXT_SOURCE_URL: {error}") from error


def _allow_insecure_source_http() -> bool:
    raw = os.environ.get("SOURCE_ALLOW_INSECURE_HTTP", "0").strip().lower()
    return raw in {"1", "true", "yes"}


def _build_source_match_preview_ttl() -> float:
    raw = os.environ.get("SOURCE_MATCH_PREVIEW_TTL_SECONDS", "300").strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError("SOURCE_MATCH_PREVIEW_TTL_SECONDS must be a positive number") from error
    if value <= 0:
        raise RuntimeError("SOURCE_MATCH_PREVIEW_TTL_SECONDS must be a positive number")
    return value


def _build_optional_event_bus():
    path = os.environ.get("EVENT_BUS_PATH", "").strip()
    return SQLiteEventBus(path) if path else None


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
    event_bus = _build_optional_event_bus()
    shared_ephemeral_store_path = os.environ.get("SHARED_EPHEMERAL_STORE_PATH", "").strip() or None
    oauth_service = build_zhihu_oauth_service()
    return create_app(
        repository,
        _build_provider(),
        _build_candidate_source(),
        content_source=_build_content_source(),
        personal_context_source=_build_personal_context_source(),
        oauth_service=oauth_service,
        source_match_preview_ttl_seconds=_build_source_match_preview_ttl(),
        sync_window_seconds=_build_sync_window(),
        event_bus=event_bus,
        shared_ephemeral_store_path=shared_ephemeral_store_path,
    )


app = _build_app()

__all__ = ("app",)
