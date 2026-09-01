"""Server-side HTTPS/OAuth JSON adapters for authorized platform wrappers.

These adapters intentionally speak a tiny vendor-neutral POST contract.  A
deployment-specific Zhihu CLI/MCP/OAuth gateway owns token refresh and
platform fields; the orchestrator receives only normalized Pydantic records.
Tokens are sent in an Authorization header and are never included in errors,
URLs, logs, or API responses.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.domain import ContentSignal, ParticipantSeed, PersonalContextScope, PersonalContextSignal

from .base import CandidateSourceError, ContentSignalSourceError, PersonalContextSourceError


def _validate_endpoint(endpoint: str, *, allow_insecure_http: bool) -> str:
    value = endpoint.strip()
    parsed = urlparse(value)
    allowed_schemes = {"https"} | ({"http"} if allow_insecure_http else set())
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        expected = "https" if not allow_insecure_http else "http or https"
        raise ValueError(f"source endpoint must be an absolute {expected} URL")
    if parsed.username or parsed.password:
        raise ValueError("source endpoint must not contain credentials")
    return value


class _HttpJsonSource:
    error_type = RuntimeError

    def __init__(
        self,
        endpoint: str,
        *,
        token: str | None = None,
        timeout_seconds: float = 5.0,
        max_output_bytes: int = 1_000_000,
        allow_insecure_http: bool = False,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("source timeout must be positive")
        if max_output_bytes <= 0:
            raise ValueError("source max output must be positive")
        self.endpoint = _validate_endpoint(endpoint, allow_insecure_http=allow_insecure_http)
        self._token = token.strip() if token is not None and token.strip() else None
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def _request_sync(self, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "zuoyizhuo-orchestrator/0.1",
        }
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        request = Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", 200))
                if status < 200 or status >= 300:
                    raise self.error_type("authorized source returned an unsuccessful response")
                chunks: list[bytes] = []
                total = 0
                while chunk := response.read(64 * 1024):
                    total += len(chunk)
                    if total > self.max_output_bytes:
                        raise self.error_type("authorized source output is too large")
                    chunks.append(chunk)
            try:
                return json.loads(b"".join(chunks).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise self.error_type("authorized source returned invalid JSON") from error
        except self.error_type:
            raise
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise self.error_type("authorized source request failed") from error

    async def _request(self, payload: dict[str, Any]) -> Any:
        try:
            return await asyncio.to_thread(self._request_sync, payload)
        except self.error_type:
            raise
        except Exception as error:
            raise self.error_type("authorized source request failed") from error


class HttpCandidateSource(_HttpJsonSource):
    """Fetch normalized candidate seeds from an authorized gateway."""

    error_type = CandidateSourceError

    async def search(self, *, query: str, limit: int) -> Sequence[ParticipantSeed]:
        if not query.strip():
            raise CandidateSourceError("candidate source query must be non-empty")
        if limit <= 0:
            raise CandidateSourceError("candidate source limit must be positive")
        payload = await self._request({"query": query, "limit": limit})
        rows = payload.get("candidates") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise CandidateSourceError("candidate source returned invalid candidates")
        try:
            return [ParticipantSeed.model_validate(item) for item in rows[:limit]]
        except (TypeError, ValueError) as error:
            raise CandidateSourceError("candidate source returned invalid candidates") from error


class HttpContentSignalSource(_HttpJsonSource):
    """Fetch normalized public content signals from an authorized gateway."""

    error_type = ContentSignalSourceError

    async def search(self, *, query: str, limit: int) -> Sequence[ContentSignal]:
        if not query.strip():
            raise ContentSignalSourceError("content source query must be non-empty")
        if limit <= 0:
            raise ContentSignalSourceError("content source limit must be positive")
        payload = await self._request({"query": query, "limit": limit})
        rows = payload.get("signals") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ContentSignalSourceError("content source returned invalid signals")
        try:
            return [ContentSignal.model_validate(item) for item in rows[:limit]]
        except (TypeError, ValueError) as error:
            raise ContentSignalSourceError("content source returned invalid signals") from error


class HttpPersonalContextSource(_HttpJsonSource):
    """Fetch private, consent-scoped context from an authorized gateway."""

    error_type = PersonalContextSourceError

    async def search(
        self,
        *,
        viewer_id: str,
        scopes: Sequence[PersonalContextScope],
        query: str,
        limit: int,
    ) -> Sequence[PersonalContextSignal]:
        if not viewer_id.strip() or not query.strip():
            raise PersonalContextSourceError("personal context viewer and query are required")
        if limit <= 0:
            raise PersonalContextSourceError("personal context limit must be positive")
        payload = await self._request({
            "viewer_id": viewer_id,
            "scopes": [scope.value if hasattr(scope, "value") else str(scope) for scope in scopes],
            "query": query,
            "limit": limit,
        })
        rows = payload.get("signals") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise PersonalContextSourceError("personal context source returned invalid signals")
        try:
            return [PersonalContextSignal.model_validate(item) for item in rows[:limit]]
        except (TypeError, ValueError) as error:
            raise PersonalContextSourceError(
                "personal context source returned invalid signals"
            ) from error


__all__ = (
    "HttpCandidateSource",
    "HttpContentSignalSource",
    "HttpPersonalContextSource",
)
