from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed


def _participant(participant_id: str, role: str = "产品") -> dict:
    return {
        "participant_id": participant_id,
        "display_name": participant_id,
        "role": role,
        "declared_position": "先看现实约束",
    }


def _client_with_table(participants: list[str] | None = None) -> tuple[TestClient, InMemoryTableRepository]:
    participants = participants or ["p1"]
    repository = InMemoryTableRepository()
    repository.create(
        "table-rest",
        "企业为什么难以采用 AI？",
        [ParticipantSeed.model_validate(_participant(item)) for item in participants],
    )
    return TestClient(create_app(repository)), repository


def test_rest_add_participant_broadcasts_public_event_then_projected_state() -> None:
    client, _ = _client_with_table()
    with client.websocket_connect("/ws/tables/table-rest?participant_id=p1") as websocket:
        response = client.post("/tables/table-rest/participants", json=_participant("p2"))
        assert response.status_code == 200

        added = websocket.receive_json()
        changed = websocket.receive_json()

    assert added == {
        "type": "participant_added",
        "participant_id": "p2",
        "state_version": 1,
    }
    assert changed["type"] == "table_state_changed"
    assert changed["state"]["version"] == 1
    assert changed["state"]["participants"]["p2"]["declared_position"] is None


def test_rest_leave_broadcasts_to_all_connected_members() -> None:
    client, _ = _client_with_table(["p1", "p2"])
    with client.websocket_connect("/ws/tables/table-rest?participant_id=p1") as owner:
        with client.websocket_connect("/ws/tables/table-rest?participant_id=p2") as leaver:
            response = client.post(
                "/tables/table-rest/participants/p2/leave?viewer_id=p2"
            )
            assert response.status_code == 200

            owner_event = owner.receive_json()
            leaver_event = leaver.receive_json()
            owner_state = owner.receive_json()
            leaver_state = leaver.receive_json()

    assert owner_event == leaver_event == {
        "type": "participant_left",
        "participant_id": "p2",
        "state_version": 1,
    }
    assert owner_state["state"]["participants"] == {"p1": owner_state["state"]["participants"]["p1"]}
    assert set(leaver_state["state"]["participants"]) == {"p1"}
    assert leaver_state["state"]["participants"]["p1"]["declared_position"] is None


def test_rest_comment_broadcasts_only_after_idempotent_commit() -> None:
    client, _ = _client_with_table()
    with client.websocket_connect(
        "/ws/tables/table-rest?participant_id=observer&viewer_mode=observer"
    ) as websocket:
        assert websocket.receive_json()["type"] == "table_state_changed"
        response = client.post(
            "/tables/table-rest/comments?author_id=guest",
            json={
                "comment_id": "comment-1",
                "display_name": "访客",
                "text": "我也遇到过类似的预算约束。",
            },
        )
        assert response.status_code == 200
        event = websocket.receive_json()

    assert event == {
        "type": "comment_added",
        "comment": {
            "comment_id": "comment-1",
            "table_id": "table-rest",
            "author_id": "guest",
            "display_name": "访客",
            "text": "我也遇到过类似的预算约束。",
            "state_version": 0,
        },
        "state_version": 0,
    }


def test_rest_close_broadcasts_public_close_event_and_state() -> None:
    client, repository = _client_with_table()
    repository.append_message_once(
        "table-rest", "p1", "我亲历过采购试点，预算和责任需要澄清。", "close-1"
    )
    with client.websocket_connect("/ws/tables/table-rest?participant_id=p1") as websocket:
        response = client.post("/tables/table-rest/close?participant_id=p1")
        assert response.status_code == 200
        closed = websocket.receive_json()
        changed = websocket.receive_json()

    assert closed == {
        "type": "table_closed",
        "state_version": 2,
    }
    assert changed["type"] == "table_state_changed"
    assert changed["state"]["conversation"]["closed"] is True


def test_rest_invitation_acceptance_broadcasts_invitation_and_membership() -> None:
    client, _ = _client_with_table()
    invitation = client.post(
        "/tables/table-rest/invitations?inviter_id=p1",
        json={"candidate": _participant("p2", "研究"), "reason": "补足研究视角"},
    ).json()

    with client.websocket_connect("/ws/tables/table-rest?participant_id=p1") as websocket:
        response = client.post(
            f"/tables/table-rest/invitations/{invitation['invitation_id']}/respond?participant_id=p2",
            json={"accept": True},
        )
        assert response.status_code == 200
        updated = websocket.receive_json()
        added = websocket.receive_json()
        changed = websocket.receive_json()

    assert updated["type"] == "invitation_updated"
    assert updated["invitation"]["status"] == "accepted"
    assert updated["state_version"] == 1
    assert added == {
        "type": "participant_added",
        "participant_id": "p2",
        "state_version": 1,
    }
    assert changed["state"]["participants"]["p2"]["declared_position"] is None


def test_rest_consent_and_soft_expiry_broadcast_state_transitions() -> None:
    client, _ = _client_with_table()
    with client.websocket_connect("/ws/tables/table-rest?participant_id=p1") as websocket:
        consent = client.post(
            "/tables/table-rest/participants/p1/consent?viewer_id=p1",
            json={"profile_shared": True},
        )
        assert consent.status_code == 200
        consent_event = websocket.receive_json()
        consent_state = websocket.receive_json()

        expired = client.post(
            "/tables/table-rest/soft-expire?participant_id=p1",
            json={"reason": "问题热度已下降"},
        )
        assert expired.status_code == 200
        expiry_event = websocket.receive_json()
        expiry_state = websocket.receive_json()

    assert consent_event == {
        "type": "participant_consent_changed",
        "participant_id": "p1",
        "profile_shared": True,
        "state_version": 1,
    }
    assert consent_state["state"]["version"] == 1
    assert expiry_event == {
        "type": "table_soft_expired",
        "reason": "问题热度已下降",
        "state_version": 2,
    }
    assert expiry_state["state"]["conversation"]["soft_expired"] is True


def test_rest_sync_upgrade_broadcasts_mode_transition() -> None:
    client, repository = _client_with_table(["p1", "p2"])
    repository.append_message_once("table-rest", "p1", "先说一条现场约束。", "sync-1")
    repository.append_message_once("table-rest", "p2", "我也愿意继续深挖。", "sync-2")
    with client.websocket_connect("/ws/tables/table-rest?participant_id=p1") as websocket:
        response = client.post(
            "/tables/table-rest/sync/upgrade?participant_id=p1",
            json={
                "wants_continue": True,
                "sync_extra_value": True,
                "discussion_quality": True,
                "external_attention": True,
                "public_value": True,
            },
        )
        assert response.status_code == 200
        mode_event = websocket.receive_json()
        changed = websocket.receive_json()

    assert mode_event["type"] == "table_mode_changed"
    assert mode_event["mode"] == "sync"
    assert changed["state"]["conversation"]["mode"] == "sync"
    assert changed["state"]["version"] == mode_event["state_version"]
