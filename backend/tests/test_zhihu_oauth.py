from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
import httpx
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.auth.zhihu import ZhihuOAuthConfig, ZhihuOAuthService, build_zhihu_oauth_service


def _service(tmp_path) -> ZhihuOAuthService:
    config = ZhihuOAuthConfig(
        app_id="test-app-id",
        app_key="test-app-key",
        redirect_uri="http://localhost:8000/auth/zhihu/callback",
        encryption_key=Fernet.generate_key().decode("ascii"),
        store_path=str(tmp_path / "oauth.sqlite"),
        post_login_url="http://localhost:5173/",
        cookie_secure=False,
        state_ttl_seconds=600,
        session_ttl_seconds=3600,
    )
    return ZhihuOAuthService(config)


def test_oauth_start_callback_and_encrypted_session(
    tmp_path, monkeypatch
) -> None:
    service = _service(tmp_path)

    async def fake_exchange(authorization_code: str) -> tuple[str, int]:
        assert authorization_code == "one-time-code"
        return "oauth-secret", 1800

    monkeypatch.setattr(service, "exchange_code", fake_exchange)
    client = TestClient(create_app(oauth_service=service))
    assert client.get("/capabilities").json()["oauth_configured"] is True
    cors = client.options(
        "/auth/session",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert cors.headers["access-control-allow-credentials"] == "true"

    start = client.get("/auth/zhihu/start", follow_redirects=False)

    assert start.status_code == 303
    location = start.headers["location"]
    query = parse_qs(urlsplit(location).query)
    assert query["app_id"] == ["test-app-id"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [service.config.redirect_uri]
    assert "test-app-key" not in location
    state = query["state"][0]

    callback = client.get(
        "/auth/zhihu/callback",
        params={"authorization_code": "one-time-code", "state": state},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == "http://localhost:5173/#auth=connected"
    session = client.get("/auth/session")
    assert session.status_code == 200
    assert session.json()["authenticated"] is True
    participant_id = session.json()["participant_id"]
    assert participant_id.startswith("session-")
    assert session.json()["zhihu_connected"] is True
    assert service.store.connection_for_subject(participant_id, now=time.time()) == (
        "oauth-secret",
        session.json()["zhihu_token_expires_at"],
    )
    assert b"oauth-secret" not in (tmp_path / "oauth.sqlite").read_bytes()

    replay = client.get(
        "/auth/zhihu/callback",
        params={"authorization_code": "one-time-code", "state": state},
        follow_redirects=False,
    )
    assert replay.status_code == 400
    assert "oauth-secret" not in replay.text


def test_exchange_code_uses_server_only_official_token_contract(
    tmp_path, monkeypatch
) -> None:
    service = _service(tmp_path)
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"access_token": "server-token", "expires_in": 321}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, data, headers):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    token, expires_in = asyncio.run(service.exchange_code("authorization-code"))

    assert token == "server-token"
    assert expires_in == 321
    assert captured["url"] == "https://openapi.zhihu.com/access_token"
    assert captured["data"] == {
        "app_id": "test-app-id",
        "app_key": "test-app-key",
        "grant_type": "authorization_code",
        "redirect_uri": service.config.redirect_uri,
        "code": "authorization-code",
    }
    assert captured["headers"] == {"Accept": "application/json"}


def test_oauth_state_is_bound_to_the_original_browser_session(tmp_path) -> None:
    service = _service(tmp_path)
    client_a = TestClient(create_app(oauth_service=service))
    client_b = TestClient(create_app(oauth_service=service))

    start = client_a.get("/auth/zhihu/start", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]

    callback = client_b.get(
        "/auth/zhihu/callback",
        params={"authorization_code": "code", "state": state},
        follow_redirects=False,
    )

    assert callback.status_code == 400
    assert client_a.get("/auth/session").json()["zhihu_connected"] is False


def test_oauth_disconnect_preserves_session_but_logout_removes_it(
    tmp_path, monkeypatch
) -> None:
    service = _service(tmp_path)

    async def fake_exchange(_authorization_code: str) -> tuple[str, int]:
        return "oauth-secret", 1800

    monkeypatch.setattr(service, "exchange_code", fake_exchange)
    client = TestClient(create_app(oauth_service=service))
    start = client.get("/auth/zhihu/start", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    client.get(
        "/auth/zhihu/callback",
        params={"authorization_code": "code", "state": state},
        follow_redirects=False,
    )

    disconnected = client.post("/auth/zhihu/disconnect")
    assert disconnected.status_code == 200
    after_disconnect = client.get("/auth/session").json()
    assert after_disconnect["authenticated"] is False
    assert after_disconnect["zhihu_connected"] is False
    assert after_disconnect["session_cookie"] is True

    logged_out = client.post("/auth/logout")
    assert logged_out.status_code == 200
    after_logout = client.get("/auth/session").json()
    assert after_logout["authenticated"] is False
    assert after_logout["session_cookie"] is False


def test_oauth_configuration_is_opt_in(monkeypatch) -> None:
    for name in (
        "ZHIHU_APP_ID",
        "ZHIHU_APP_KEY",
        "ZHIHU_OAUTH_REDIRECT_URI",
        "ZHIHU_OAUTH_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    assert build_zhihu_oauth_service() is None
