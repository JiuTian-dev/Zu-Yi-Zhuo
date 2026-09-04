"""Server-side Zhihu OAuth authorization-code integration.

This module deliberately stops at the contract Zhihu has documented publicly:
authorization code exchange and a token-backed application session. The
provider's user-info endpoint and refresh/revocation contract are not public
in the current docs, so they are not guessed here.

The browser receives only an opaque HttpOnly session cookie. OAuth tokens are
encrypted before they are persisted and are never returned by an API route,
placed in a redirect URL, or passed to the frontend.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.identity import IdentityInput


COOKIE_NAME = "zuoyizhuo_session"
DEFAULT_AUTHORIZE_URL = "https://openapi.zhihu.com/authorize"
DEFAULT_TOKEN_URL = "https://openapi.zhihu.com/access_token"
DEFAULT_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
DEFAULT_STATE_TTL_SECONDS = 10 * 60
DEFAULT_TOKEN_TTL_SECONDS = 3600


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _positive_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive number") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _validate_service_url(name: str, value: str) -> str:
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1"}
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise RuntimeError(f"{name} must use HTTPS")
    if not parsed.netloc or parsed.username or parsed.password:
        raise RuntimeError(f"{name} must be an absolute URL without credentials")
    return value


@dataclass(frozen=True)
class ZhihuOAuthConfig:
    app_id: str
    app_key: str
    redirect_uri: str
    encryption_key: str
    store_path: str
    post_login_url: str
    authorize_url: str = DEFAULT_AUTHORIZE_URL
    token_url: str = DEFAULT_TOKEN_URL
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    state_ttl_seconds: float = DEFAULT_STATE_TTL_SECONDS
    session_ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS
    timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls) -> "ZhihuOAuthConfig | None":
        names = (
            "ZHIHU_APP_ID",
            "ZHIHU_APP_KEY",
            "ZHIHU_OAUTH_REDIRECT_URI",
            "ZHIHU_OAUTH_ENCRYPTION_KEY",
        )
        configured = any((os.getenv(name) or "").strip() for name in names)
        if not configured:
            return None
        missing = [name for name in names if not (os.getenv(name) or "").strip()]
        if missing:
            raise RuntimeError(
                "Zhihu OAuth configuration is incomplete: " + ", ".join(missing)
            )

        redirect_uri = os.environ["ZHIHU_OAUTH_REDIRECT_URI"].strip()
        parsed_redirect = urlsplit(redirect_uri)
        if parsed_redirect.scheme not in {"https", "http"} or not parsed_redirect.netloc:
            raise RuntimeError("ZHIHU_OAUTH_REDIRECT_URI must be an absolute URL")
        if parsed_redirect.scheme != "https" and parsed_redirect.hostname not in {
            "localhost",
            "127.0.0.1",
        }:
            raise RuntimeError("ZHIHU_OAUTH_REDIRECT_URI must use HTTPS")

        encryption_key = os.environ["ZHIHU_OAUTH_ENCRYPTION_KEY"].strip()
        try:
            Fernet(encryption_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise RuntimeError(
                "ZHIHU_OAUTH_ENCRYPTION_KEY must be a Fernet key"
            ) from error

        store_path = (
            os.getenv("ZHIHU_OAUTH_STORE_PATH", "").strip()
            or os.getenv("SHARED_EPHEMERAL_STORE_PATH", "").strip()
            or str(Path("runtime") / "oauth.sqlite")
        )
        post_login_url = os.getenv("ZHIHU_OAUTH_POST_LOGIN_URL", "").strip()
        if not post_login_url:
            post_login_url = urlunsplit(
                (parsed_redirect.scheme, parsed_redirect.netloc, "/", "", "")
            )
        parsed_post_login = urlsplit(post_login_url)
        if parsed_post_login.scheme not in {"https", "http"} or not parsed_post_login.netloc:
            raise RuntimeError("ZHIHU_OAUTH_POST_LOGIN_URL must be an absolute URL")
        if parsed_post_login.scheme != "https" and parsed_post_login.hostname not in {
            "localhost",
            "127.0.0.1",
        }:
            raise RuntimeError("ZHIHU_OAUTH_POST_LOGIN_URL must use HTTPS")

        cookie_secure = _bool_env(
            "ZHIHU_OAUTH_COOKIE_SECURE",
            parsed_redirect.scheme == "https",
        )
        cookie_samesite = os.getenv("ZHIHU_OAUTH_COOKIE_SAMESITE", "lax").strip().lower()
        if cookie_samesite not in {"lax", "strict", "none"}:
            raise RuntimeError(
                "ZHIHU_OAUTH_COOKIE_SAMESITE must be lax, strict, or none"
            )
        if cookie_samesite == "none" and not cookie_secure:
            raise RuntimeError("SameSite=None requires a Secure OAuth cookie")

        authorize_url = _validate_service_url(
            "ZHIHU_OAUTH_AUTHORIZE_URL",
            os.getenv("ZHIHU_OAUTH_AUTHORIZE_URL", DEFAULT_AUTHORIZE_URL).strip(),
        )
        token_url = _validate_service_url(
            "ZHIHU_OAUTH_TOKEN_URL",
            os.getenv("ZHIHU_OAUTH_TOKEN_URL", DEFAULT_TOKEN_URL).strip(),
        )

        return cls(
            app_id=os.environ["ZHIHU_APP_ID"].strip(),
            app_key=os.environ["ZHIHU_APP_KEY"].strip(),
            redirect_uri=redirect_uri,
            encryption_key=encryption_key,
            store_path=store_path,
            post_login_url=post_login_url,
            authorize_url=authorize_url,
            token_url=token_url,
            cookie_secure=cookie_secure,
            cookie_samesite=cookie_samesite,
            state_ttl_seconds=_positive_env(
                "ZHIHU_OAUTH_STATE_TTL_SECONDS", DEFAULT_STATE_TTL_SECONDS
            ),
            session_ttl_seconds=_positive_env(
                "ZHIHU_OAUTH_SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS
            ),
            timeout_seconds=_positive_env("ZHIHU_OAUTH_TIMEOUT_SECONDS", 5.0),
        )


class SQLiteOAuthStore:
    """Small encrypted token/session store shared by backend workers."""

    def __init__(self, path: str, encryption_key: str) -> None:
        self.path = path
        self._fernet = Fernet(encryption_key.encode("ascii"))
        self._memory_connection = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if path == ":memory:"
            else None
        )
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            self._memory_connection.execute("PRAGMA busy_timeout=5000")
            return self._memory_connection
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            if self.path != ":memory:":
                connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS oauth_sessions (
                    session_hash TEXT PRIMARY KEY,
                    participant_id TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_attempts (
                    state_hash TEXT PRIMARY KEY,
                    session_hash TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_connections (
                    session_hash TEXT PRIMARY KEY,
                    encrypted_access_token BLOB NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )

    def create_session(self, *, now: float, ttl_seconds: float) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        session_hash = _digest(token)
        participant_id = f"session-{uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO oauth_sessions(session_hash, participant_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (session_hash, participant_id, now, now + ttl_seconds),
            )
        return token, participant_id

    def ensure_session(
        self, token: str | None, *, now: float, ttl_seconds: float
    ) -> tuple[str, str]:
        if token:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT participant_id, expires_at FROM oauth_sessions WHERE session_hash = ?",
                    (_digest(token),),
                ).fetchone()
            if row is not None and float(row[1]) > now:
                return token, str(row[0])
        return self.create_session(now=now, ttl_seconds=ttl_seconds)

    def issue_state(
        self, session_token: str, *, now: float, ttl_seconds: float
    ) -> str:
        state = secrets.token_urlsafe(32)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO oauth_attempts(state_hash, session_hash, expires_at) VALUES (?, ?, ?)",
                (_digest(state), _digest(session_token), now + ttl_seconds),
            )
        return state

    def consume_state(
        self, state: str, session_token: str, *, now: float
    ) -> str | None:
        state_hash = _digest(state)
        session_hash = _digest(session_token)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_hash, expires_at FROM oauth_attempts WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            connection.execute(
                "DELETE FROM oauth_attempts WHERE state_hash = ?", (state_hash,)
            )
        if row is None or float(row[1]) <= now:
            return None
        if not hmac.compare_digest(str(row[0]), session_hash):
            return None
        return session_hash

    def save_connection(
        self,
        session_token: str,
        access_token: str,
        *,
        now: float,
        expires_in: int,
        session_ttl_seconds: float,
    ) -> str:
        session_hash = _digest(session_token)
        expires_at = now + max(1, expires_in)
        encrypted = self._fernet.encrypt(access_token.encode("utf-8"))
        with self._connect() as connection:
            row = connection.execute(
                "SELECT expires_at FROM oauth_sessions WHERE session_hash = ?",
                (session_hash,),
            ).fetchone()
            if row is None or float(row[0]) <= now:
                raise ValueError("oauth session expired")
            connection.execute(
                "INSERT INTO oauth_connections(session_hash, encrypted_access_token, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(session_hash) DO UPDATE SET encrypted_access_token=excluded.encrypted_access_token, expires_at=excluded.expires_at",
                (session_hash, encrypted, expires_at),
            )
            connection.execute(
                "UPDATE oauth_sessions SET expires_at = ? WHERE session_hash = ?",
                (now + session_ttl_seconds, session_hash),
            )
        return session_hash

    def subject_for_session(self, session_token: str | None, *, now: float) -> str | None:
        if not session_token:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT s.participant_id FROM oauth_sessions s JOIN oauth_connections c ON c.session_hash = s.session_hash "
                "WHERE s.session_hash = ? AND s.expires_at > ? AND c.expires_at > ?",
                (_digest(session_token), now, now),
            ).fetchone()
        return str(row[0]) if row else None

    def connection_for_subject(
        self, participant_id: str, *, now: float
    ) -> tuple[str, float] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT c.encrypted_access_token, c.expires_at FROM oauth_connections c "
                "JOIN oauth_sessions s ON s.session_hash = c.session_hash "
                "WHERE s.participant_id = ? AND s.expires_at > ? AND c.expires_at > ?",
                (participant_id, now, now),
            ).fetchone()
        if row is None:
            return None
        try:
            token = self._fernet.decrypt(bytes(row[0])).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as error:
            raise RuntimeError("stored OAuth connection is invalid") from error
        return token, float(row[1])

    def disconnect(self, session_token: str | None) -> None:
        if not session_token:
            return
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM oauth_connections WHERE session_hash = ?",
                (_digest(session_token),),
            )

    def delete_session(self, session_token: str | None) -> None:
        if not session_token:
            return
        session_hash = _digest(session_token)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM oauth_attempts WHERE session_hash = ?", (session_hash,)
            )
            connection.execute(
                "DELETE FROM oauth_connections WHERE session_hash = ?", (session_hash,)
            )
            connection.execute(
                "DELETE FROM oauth_sessions WHERE session_hash = ?", (session_hash,)
            )


class ZhihuOAuthError(RuntimeError):
    """A safe, user-facing OAuth failure without provider/token details."""


class ZhihuOAuthService:
    def __init__(
        self,
        config: ZhihuOAuthConfig,
        *,
        store: SQLiteOAuthStore | None = None,
    ) -> None:
        self.config = config
        self.store = store or SQLiteOAuthStore(config.store_path, config.encryption_key)

    def authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "redirect_uri": self.config.redirect_uri,
                "app_id": self.config.app_id,
                "response_type": "code",
                "state": state,
            }
        )
        separator = "&" if "?" in self.config.authorize_url else "?"
        return f"{self.config.authorize_url}{separator}{query}"

    async def exchange_code(self, authorization_code: str) -> tuple[str, int]:
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self.config.token_url,
                    data={
                        "app_id": self.config.app_id,
                        "app_key": self.config.app_key,
                        "grant_type": "authorization_code",
                        "redirect_uri": self.config.redirect_uri,
                        "code": authorization_code,
                    },
                    headers={"Accept": "application/json"},
                )
            if response.status_code < 200 or response.status_code >= 300:
                raise ZhihuOAuthError("知乎授权暂时不可用")
            payload = response.json()
        except ZhihuOAuthError:
            raise
        except (httpx.HTTPError, ValueError, TypeError):
            raise ZhihuOAuthError("知乎授权暂时不可用") from None

        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token.strip():
            raise ZhihuOAuthError("知乎授权没有返回有效凭据")
        expires_in = payload.get("expires_in", DEFAULT_TOKEN_TTL_SECONDS)
        try:
            expires_in = int(expires_in)
        except (TypeError, ValueError):
            raise ZhihuOAuthError("知乎授权返回的有效期无效") from None
        if expires_in <= 0:
            raise ZhihuOAuthError("知乎授权返回的有效期无效")
        return access_token.strip(), expires_in

    def identity_resolver(self, request: IdentityInput) -> str | None:
        return self.store.subject_for_session(
            request.cookies.get(COOKIE_NAME), now=time.time()
        )

    def session_view(self, request: Request) -> dict[str, Any]:
        token = request.cookies.get(COOKIE_NAME)
        participant_id = self.identity_resolver(request)
        connection = (
            self.store.connection_for_subject(participant_id, now=time.time())
            if participant_id
            else None
        )
        return {
            "authenticated": participant_id is not None,
            "participant_id": participant_id,
            "zhihu_connected": connection is not None,
            "zhihu_token_expires_at": connection[1] if connection else None,
            "session_cookie": bool(token),
        }


def _result_url(base: str, result: str) -> str:
    parsed = urlsplit(base)
    fragment = urlencode({"auth": result})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, fragment))


def _clear_cookie(
    response: Response,
    *,
    secure: bool,
    samesite: Literal["lax", "strict", "none"],
) -> None:
    response.delete_cookie(
        COOKIE_NAME, secure=secure, httponly=True, samesite=samesite
    )


def register_zhihu_auth_routes(api: FastAPI, service: ZhihuOAuthService) -> None:
    """Register the optional OAuth routes on the existing product API."""

    @api.get("/auth/zhihu/start")
    def start_zhihu_oauth(request: Request) -> Response:
        session_token, _participant_id = service.store.ensure_session(
            request.cookies.get(COOKIE_NAME),
            now=time.time(),
            ttl_seconds=service.config.session_ttl_seconds,
        )
        state = service.store.issue_state(
            session_token,
            now=time.time(),
            ttl_seconds=service.config.state_ttl_seconds,
        )
        response = RedirectResponse(
            service.authorization_url(state), status_code=status.HTTP_303_SEE_OTHER
        )
        response.set_cookie(
            COOKIE_NAME,
            session_token,
            max_age=int(service.config.session_ttl_seconds),
            secure=service.config.cookie_secure,
            httponly=True,
            samesite=service.config.cookie_samesite,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @api.get("/auth/zhihu/callback")
    async def finish_zhihu_oauth(request: Request) -> Response:
        error = request.query_params.get("error")
        if error:
            response = RedirectResponse(
                _result_url(service.config.post_login_url, "denied"),
                status_code=status.HTTP_303_SEE_OTHER,
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        authorization_code = request.query_params.get("authorization_code")
        state = request.query_params.get("state")
        session_token = request.cookies.get(COOKIE_NAME)
        if not authorization_code or not state or not session_token:
            return JSONResponse(
                {"detail": "OAuth callback is missing required parameters"},
                status_code=status.HTTP_400_BAD_REQUEST,
                headers={"Cache-Control": "no-store"},
            )
        if service.store.consume_state(state, session_token, now=time.time()) is None:
            return JSONResponse(
                {"detail": "OAuth callback could not be verified"},
                status_code=status.HTTP_400_BAD_REQUEST,
                headers={"Cache-Control": "no-store"},
            )
        try:
            access_token, expires_in = await service.exchange_code(authorization_code)
            service.store.save_connection(
                session_token,
                access_token,
                now=time.time(),
                expires_in=expires_in,
                session_ttl_seconds=service.config.session_ttl_seconds,
            )
        except (ZhihuOAuthError, ValueError):
            return JSONResponse(
                {"detail": "知乎授权暂时没有完成，请稍后重试"},
                status_code=status.HTTP_502_BAD_GATEWAY,
                headers={"Cache-Control": "no-store"},
            )
        response = RedirectResponse(
            _result_url(service.config.post_login_url, "connected"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @api.get("/auth/session")
    def get_auth_session(request: Request) -> dict[str, Any]:
        return service.session_view(request)

    @api.post("/auth/logout")
    def logout(request: Request) -> Response:
        service.store.delete_session(request.cookies.get(COOKIE_NAME))
        response = JSONResponse({"ok": True})
        _clear_cookie(
            response,
            secure=service.config.cookie_secure,
            samesite=service.config.cookie_samesite,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @api.post("/auth/zhihu/disconnect")
    def disconnect_zhihu(request: Request) -> Response:
        service.store.disconnect(request.cookies.get(COOKIE_NAME))
        response = JSONResponse({"ok": True})
        response.headers["Cache-Control"] = "no-store"
        return response


def build_zhihu_oauth_service() -> ZhihuOAuthService | None:
    config = ZhihuOAuthConfig.from_env()
    return ZhihuOAuthService(config) if config else None


__all__ = (
    "COOKIE_NAME",
    "DEFAULT_AUTHORIZE_URL",
    "DEFAULT_TOKEN_URL",
    "SQLiteOAuthStore",
    "ZhihuOAuthConfig",
    "ZhihuOAuthError",
    "ZhihuOAuthService",
    "build_zhihu_oauth_service",
    "register_zhihu_auth_routes",
)
