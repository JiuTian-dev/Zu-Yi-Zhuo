from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository


def _client_with_table() -> tuple[TestClient, InMemoryTableRepository]:
    repository = InMemoryTableRepository()
    repository.create(
        "table-ws",
        "企业为什么难以采用 AI？",
        [],
    )
    return TestClient(create_app(repository)), repository


def _participant(participant_id: str, role: str = "产品") -> dict:
    return {
        "participant_id": participant_id,
        "display_name": participant_id,
        "role": role,
        "declared_position": "先看现实约束",
        "relevant_experience": [
            {"text": "采购试点的现场经验", "source_ref": "本人经历"}
        ],
    }


def test_human_message_commits_contract_and_persists_host_intervention() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "human_message", "message_id": "msg-1", "participant_id": "p1",
            "text": "我亲历过采购，预算和责任需要澄清。", "client_ts": "2026-08-31T12:00:00Z",
        })
        committed = websocket.receive_json()
        action = websocket.receive_json()
        changed = websocket.receive_json()

    assert committed == {
        "type": "message_committed",
        "message": {
            "message_id": "msg-1", "participant_id": "p1",
            "text": "我亲历过采购，预算和责任需要澄清。", "client_ts": "2026-08-31T12:00:00Z",
        },
    }
    assert changed["type"] == "table_state_changed"
    assert (changed["phase"], changed["momentum"], changed["close_readiness"]) == (
        "explore", "high", "low"
    )
    assert changed["state"]["version"] == 4
    assert changed["state"]["intervention"]["last_action"] == "PASS"
    assert changed["state"]["intervention"]["human_turns_since_last_intervention"] == 0
    assert action["type"] == "agent_action"
    assert action["action"] == "PASS"
    assert action["state_version"] == changed["state"]["version"]
    assert action["gate"]["should_speak"] is True
    assert action["route"]["action"] == "PASS"
    assert repository.get("table-ws").intervention.last_action.value == "PASS"
    assert [state.version for state in repository.replay("table-ws")] == [0, 1, 2, 3, 4]


def test_debug_join_unknown_event_and_silence_are_structured() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "研究")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({"type": "request_debug_state"})
        assert websocket.receive_json()["state"]["version"] == 2

        websocket.send_json({"type": "participant_joined", "participant_id": "p1"})
        joined = websocket.receive_json()
        assert joined["type"] == "table_state_changed"
        assert joined["state"]["version"] == 2

        websocket.send_json({"type": "not_a_real_event"})
        assert websocket.receive_json()["code"] == "unknown_event"

        websocket.send_json({
            "type": "human_message", "message_id": "msg-2", "participant_id": "p1",
            "text": "我们先界定问题。", "client_ts": "2026-08-31T12:01:00Z",
        })
        assert websocket.receive_json()["type"] == "message_committed"
        assert websocket.receive_json()["type"] == "table_state_changed"
        websocket.send_json({"type": "request_debug_state"})
        # This is the next event, proving that SILENCE did not enqueue agent_action.
        assert websocket.receive_json()["type"] == "table_state_changed"


def test_participant_events_only_accept_the_query_participant_id() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({"type": "participant_joined", "participant_id": "missing"})
        assert websocket.receive_json()["code"] == "invalid_event"
        websocket.send_json({"type": "participant_left", "participant_id": "p1"})
        left = websocket.receive_json()

    assert left["type"] == "table_state_changed"
    assert left["state"]["participants"] == {}

    with client.websocket_connect("/ws/tables/table-ws?participant_id=ghost") as websocket:
        websocket.send_json({"type": "participant_joined", "participant_id": "ghost"})
        error = websocket.receive_json()

    assert error["code"] == "invalid_event"
    assert "unknown participant" in error["detail"]


def test_legacy_human_message_is_a_structured_error_without_closing_connection() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({"type": "human_message", "turn_id": 1, "text": "旧消息"})
        assert websocket.receive_json()["code"] == "invalid_payload"
        websocket.send_json({"type": "request_debug_state"})
        assert websocket.receive_json()["type"] == "table_state_changed"


def test_unsafe_message_is_intercepted_before_turn_replay_or_host_action() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    versions_before = [state.version for state in repository.replay("table-ws")]

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "human_message", "message_id": "unsafe-1", "participant_id": "p1",
            "text": "我会威胁你。", "client_ts": "2026-08-31T12:02:00Z",
        })
        event = websocket.receive_json()
        websocket.send_json({
            "type": "human_message", "message_id": "safe-after-unsafe", "participant_id": "p1",
            "text": "我们讨论采购的约束。", "client_ts": "2026-08-31T12:03:00Z",
        })
        paused = websocket.receive_json()
        websocket.send_json({"type": "request_debug_state"})
        debug = websocket.receive_json()

    assert event["type"] == "safety_enforced"
    assert event["decision"]["action"] in {"pause", "intercept", "remove"}
    assert event["decision"]["level"] == "critical"
    assert event["state"]["conversation"]["safety_level"] == "critical"
    assert paused["type"] == "error" and paused["code"] == "table_paused"
    assert repository.turns("table-ws") == []
    assert [state.version for state in repository.replay("table-ws")] == [
        *versions_before, versions_before[-1] + 1,
    ]
    assert debug["type"] == "table_state_changed"
    assert debug["state"]["version"] == event["state"]["version"]
    assert debug["state"]["conversation"]["safety_level"] == "critical"
    assert debug["state"]["conversation"]["state"] == "safety_paused"
