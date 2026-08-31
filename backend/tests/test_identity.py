import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="桌内立场",
    )


def _repository() -> InMemoryTableRepository:
    repository = InMemoryTableRepository()
    repository.create("identity-table", "Q", [_seed("p1"), _seed("p2")])
    return repository


def _header_identity(request) -> str | None:
    return request.headers.get("x-user-id")


def test_injected_identity_resolver_cross_checks_self_scoped_rest_routes() -> None:
    client = TestClient(create_app(_repository(), identity_resolver=_header_identity))

    missing = client.get("/participants/p1/no-match?viewer_id=p1")
    mismatch = client.get(
        "/participants/p1/no-match?viewer_id=p1",
        headers={"X-User-ID": "p2"},
    )
    valid = client.get(
        "/participants/p1/no-match?viewer_id=p1",
        headers={"X-User-ID": "p1"},
    )

    assert missing.status_code == 401
    assert mismatch.status_code == 403
    assert valid.status_code == 200


def test_injected_identity_resolver_protects_invitation_preference_update() -> None:
    client = TestClient(create_app(_repository(), identity_resolver=_header_identity))

    missing = client.put(
        "/tables/identity-table/participants/p1/invitation-preference?viewer_id=p1",
        json={"preference": "many"},
    )
    mismatch = client.put(
        "/tables/identity-table/participants/p1/invitation-preference?viewer_id=p1",
        headers={"X-User-ID": "p2"},
        json={"preference": "many"},
    )
    valid = client.put(
        "/tables/identity-table/participants/p1/invitation-preference?viewer_id=p1",
        headers={"X-User-ID": "p1"},
        json={"preference": "many"},
    )

    assert missing.status_code == 401
    assert mismatch.status_code == 403
    assert valid.status_code == 200


def test_injected_identity_resolver_cross_checks_participant_websocket_handshake() -> None:
    client = TestClient(create_app(_repository(), identity_resolver=_header_identity))

    with client.websocket_connect(
        "/ws/tables/identity-table?participant_id=p1",
        headers={"X-User-ID": "p1"},
    ) as websocket:
        websocket.send_json({"type": "request_debug_state"})
        assert websocket.receive_json()["type"] == "table_state_changed"

    with client.websocket_connect(
        "/ws/tables/identity-table?participant_id=p1",
        headers={"X-User-ID": "p2"},
    ) as websocket:
        assert websocket.receive_json() == {
            "type": "error",
            "code": "identity_mismatch",
            "detail": "authenticated subject does not match participant_id",
        }
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()

    with client.websocket_connect(
        "/ws/tables/identity-table?participant_id=p1",
    ) as websocket:
        assert websocket.receive_json() == {
            "type": "error",
            "code": "authentication_required",
            "detail": "authentication required",
        }
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_websocket_origin_allowlist_rejects_cross_site_handshakes() -> None:
    client = TestClient(create_app(
        _repository(),
        websocket_allowed_origins=["https://app.example.com"],
    ))

    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(
            "/ws/tables/identity-table?participant_id=p1",
            headers={"Origin": "https://evil.example.com"},
        ):
            pass
    assert rejected.value.code == 1008

    with pytest.raises(WebSocketDisconnect) as missing:
        with client.websocket_connect("/ws/tables/identity-table?participant_id=p1"):
            pass
    assert missing.value.code == 1008

    with client.websocket_connect(
        "/ws/tables/identity-table?participant_id=p1",
        headers={"Origin": "https://app.example.com"},
    ) as websocket:
        websocket.send_json({"type": "request_debug_state"})
        assert websocket.receive_json()["type"] == "table_state_changed"


def test_websocket_origin_allowlist_rejects_wildcards() -> None:
    with pytest.raises(ValueError, match="must not contain wildcards"):
        create_app(_repository(), websocket_allowed_origins=["*"])


def test_websocket_origin_allowlist_can_be_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("WS_ALLOWED_ORIGINS", "https://app.example.com, https://admin.example.com")
    client = TestClient(create_app(_repository()))

    with client.websocket_connect(
        "/ws/tables/identity-table?participant_id=p1",
        headers={"Origin": "https://admin.example.com"},
    ) as websocket:
        websocket.send_json({"type": "request_debug_state"})
        assert websocket.receive_json()["type"] == "table_state_changed"


def test_websocket_frame_limit_can_be_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("WS_MAX_FRAME_BYTES", "128")
    client = TestClient(create_app(_repository()))

    with client.websocket_connect("/ws/tables/identity-table?participant_id=p1") as websocket:
        websocket.send_json({"type": "request_debug_state", "padding": "x" * 128})
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_json()

    assert disconnected.value.code == 1009


def test_websocket_frame_limit_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        create_app(_repository(), websocket_max_frame_bytes=0)
