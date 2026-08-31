import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from starlette.websockets import WebSocketDisconnect

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import Action, GateDecision, GroundingCard, RouteDecision


class _HostProvider:
    model = "test-host"

    def __init__(self, text: str):
        self.text_value = text
        self.calls = 0

    async def text(self, task, messages, config=None):
        self.calls += 1
        return self.text_value


def _client_with_table(provider=None) -> tuple[TestClient, InMemoryTableRepository]:
    repository = InMemoryTableRepository()
    repository.create(
        "table-ws",
        "企业为什么难以采用 AI？",
        [],
    )
    return TestClient(create_app(repository, provider)), repository


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


def test_oversized_websocket_frame_closes_with_message_too_big() -> None:
    client, _repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({"type": "request_debug_state", "padding": "x" * (64 * 1024)})
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_json()

    assert disconnected.value.code == 1009


def test_overlong_human_text_is_rejected_without_persistence() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "human_message",
            "message_id": "too-long",
            "participant_id": "p1",
            "text": "x" * 4001,
            "client_ts": 1,
        })
        assert websocket.receive_json() == {
            "type": "error",
            "code": "invalid_payload",
            "detail": "event payload does not match its contract",
        }
        websocket.send_json({"type": "request_debug_state"})
        assert websocket.receive_json()["state"]["version"] == 1

    assert repository.turns("table-ws") == []


def test_injected_provider_rewrites_host_text_but_keeps_action_and_audit() -> None:
    provider = _HostProvider("先把预算验收的具体边界说清，再继续比较。")
    client, repository = _client_with_table(provider)
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "human_message", "message_id": "provider-1", "participant_id": "p1",
            "text": "我亲历过采购，预算和责任需要澄清。", "client_ts": "2026-08-31T12:00:00Z",
        })
        assert websocket.receive_json()["type"] == "message_committed"
        action = websocket.receive_json()
        changed = websocket.receive_json()

    assert provider.calls == 1
    assert action["action"] == "PASS"
    assert action["text"] == provider.text_value
    assert changed["state"]["intervention"]["last_action"] == "PASS"
    assert repository.interventions("table-ws")[0].model == "test-host"


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
    assert "采购试点的现场经验" not in action["text"]
    assert action["gate"]["should_speak"] is True
    assert action["route"]["action"] == "PASS"
    assert repository.get("table-ws").intervention.last_action.value == "PASS"
    assert [state.version for state in repository.replay("table-ws")] == [0, 1, 2, 3, 4]
    audit = client.get("/tables/table-ws/interventions")
    assert audit.status_code == 200
    assert len(audit.json()) == 1
    assert audit.json()[0]["action"] == "PASS"
    assert audit.json()[0]["state_version"] == 4


def test_duplicate_message_id_is_rejected_without_replaying_the_turn() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    payload = {
        "type": "human_message", "message_id": "retry-1", "participant_id": "p1",
        "text": "我亲历过采购，预算和责任需要澄清。", "client_ts": "2026-08-31T12:00:00Z",
    }
    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json(payload)
        assert websocket.receive_json()["type"] == "message_committed"
        assert websocket.receive_json()["type"] == "agent_action"
        changed = websocket.receive_json()
        assert changed["type"] == "table_state_changed"
        committed_version = changed["state"]["version"]

        websocket.send_json(payload)
        assert websocket.receive_json() == {
            "type": "error",
            "code": "duplicate_message",
            "detail": "message_id is already committed for this table",
        }
        websocket.send_json({"type": "request_debug_state"})
        debug = websocket.receive_json()

    assert debug["state"]["version"] == committed_version
    assert len(repository.turns("table-ws")) == 1
    assert len(repository.interventions("table-ws")) == 1


def test_intervention_audit_receives_post_turn_reflection() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "human_message", "message_id": "reflect-0", "participant_id": "p1",
            "text": "我亲历过采购，预算和责任需要澄清。", "client_ts": "2026-08-31T12:00:00Z",
        })
        assert websocket.receive_json()["type"] == "message_committed"
        assert websocket.receive_json()["type"] == "agent_action"
        assert websocket.receive_json()["type"] == "table_state_changed"

        for index in (1, 2):
            websocket.send_json({
                "type": "human_message", "message_id": f"reflect-{index}", "participant_id": "p1",
                "text": f"补充第 {index} 条现场信息。", "client_ts": f"2026-08-31T12:0{index}:00Z",
            })
            assert websocket.receive_json()["type"] == "message_committed"
            event = websocket.receive_json()
            while event["type"] != "table_state_changed":
                event = websocket.receive_json()
            if index == 2:
                reflected = websocket.receive_json()

    assert reflected["type"] == "intervention_reflected"
    assert reflected["record"]["outcome"] is not None
    assert reflected["record"]["reflection"] is not None
    audit = client.get("/tables/table-ws/interventions").json()
    assert audit[0]["reflection"]["evidence_turns"] == [3]


def test_public_table_events_are_broadcast_to_other_connections() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as sender:
        with client.websocket_connect("/ws/tables/table-ws?participant_id=p2") as observer:
            sender.send_json({
                "type": "human_message", "message_id": "broadcast-1", "participant_id": "p1",
                "text": "我亲历过采购，预算和责任需要澄清。", "client_ts": "2026-08-31T12:00:00Z",
            })
            sender_message = sender.receive_json()
            observer_message = observer.receive_json()
            sender_action = sender.receive_json()
            observer_action = observer.receive_json()
            sender_state = sender.receive_json()
            observer_state = observer.receive_json()

    assert sender_message == observer_message
    assert sender_action == observer_action
    assert observer_message["type"] == "message_committed"
    assert observer_message["message"]["participant_id"] == "p1"
    assert observer_action["type"] == "agent_action"
    assert observer_state["type"] == "table_state_changed"
    assert sender_state["state"]["participants"]["p1"]["declared_position"] == "先看现实约束"
    assert observer_state["state"]["participants"]["p1"]["declared_position"] is None
    assert observer_state["state"]["participants"]["p1"]["unused_relevant_experience"] == []


def test_websocket_consent_is_self_scoped_and_updates_peer_projection() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as owner:
        with client.websocket_connect("/ws/tables/table-ws?participant_id=p2") as peer:
            owner.send_json({
                "type": "participant_consent", "participant_id": "p1", "profile_shared": True,
            })
            assert owner.receive_json() == peer.receive_json() == {
                "type": "participant_consent_changed", "participant_id": "p1", "profile_shared": True,
            }
            owner_state = owner.receive_json()
            peer_state = peer.receive_json()
            assert owner_state["state"]["participants"]["p1"]["declared_position"] == "先看现实约束"
            assert peer_state["state"]["participants"]["p1"]["declared_position"] == "先看现实约束"

            owner.send_json({
                "type": "participant_consent", "participant_id": "p2", "profile_shared": True,
            })
            error = owner.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "invalid_event"
    assert "participant_id must match" in error["detail"]


def test_websocket_invitation_preference_is_self_scoped_and_idempotent() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as owner:
        with client.websocket_connect("/ws/tables/table-ws?participant_id=p2") as peer:
            owner.send_json({
                "type": "participant_invitation_preference",
                "participant_id": "p1",
                "preference": "many",
            })
            expected = {
                "type": "participant_invitation_preference_changed",
                "participant_id": "p1",
                "preference": "many",
                "state_version": 3,
            }
            assert owner.receive_json() == peer.receive_json() == expected
            owner_state = owner.receive_json()
            peer_state = peer.receive_json()
            assert owner_state["state"]["participants"]["p1"]["roundtable_invite_preference"] == "many"
            assert peer_state["state"]["participants"]["p1"]["roundtable_invite_preference"] == "many"

            owner.send_json({
                "type": "participant_invitation_preference",
                "participant_id": "p1",
                "preference": "many",
            })
            owner.send_json({"type": "request_debug_state"})
            assert owner.receive_json()["state"]["version"] == 3

            owner.send_json({
                "type": "participant_invitation_preference",
                "participant_id": "p2",
                "preference": "none",
            })
            error = owner.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "invalid_event"
    assert "participant_id must match" in error["detail"]
    assert repository.get("table-ws").version == 3


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


def test_request_nudge_turns_unanswered_first_expression_into_audited_probe() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "human_message", "message_id": "nudge-1", "participant_id": "p1",
            "text": "我有一个初步感受，但还没想清楚。", "client_ts": 1,
        })
        assert websocket.receive_json()["type"] == "message_committed"
        first_state = websocket.receive_json()
        assert first_state["type"] == "table_state_changed"
        assert repository.interventions("table-ws") == []

        websocket.send_json({"type": "request_nudge"})
        action = websocket.receive_json()
        changed = websocket.receive_json()

    assert action["type"] == "agent_action"
    assert action["action"] == "PROBE"
    assert action["route"] == {
        "action": "PROBE",
        "target_participant_id": None,
        "evidence_turns": [1],
        "confidence": 0.72,
    }
    assert action["gate"]["reasons_to_speak"] == ["首条表达暂未获得自然回应，主动递一句轻问"]
    assert changed["state"]["version"] == 4
    audit = repository.interventions("table-ws")[0]
    assert audit.action is Action.PROBE
    assert audit.reasons_to_speak[0].text == "首条表达暂未获得自然回应，主动递一句轻问"


def test_request_nudge_requires_evidence_and_respects_intervention_cooldown() -> None:
    client, _repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({"type": "request_nudge"})
        assert websocket.receive_json() == {
            "type": "error",
            "code": "nudge_unavailable",
            "detail": "a cold-start nudge requires a committed human turn",
        }

        websocket.send_json({
            "type": "human_message", "message_id": "nudge-2", "participant_id": "p1",
            "text": "我亲历过采购，预算和责任需要澄清。", "client_ts": 2,
        })
        assert websocket.receive_json()["type"] == "message_committed"
        assert websocket.receive_json()["type"] == "agent_action"
        assert websocket.receive_json()["type"] == "table_state_changed"

        websocket.send_json({"type": "request_nudge"})
        assert websocket.receive_json() == {
            "type": "error",
            "code": "intervention_cooldown",
            "detail": "two human turns are required between Agent interventions",
        }
        websocket.send_json({"type": "request_debug_state"})
        # This is the next event, proving that SILENCE did not enqueue agent_action.
        assert websocket.receive_json()["type"] == "table_state_changed"


def test_request_nudge_rejects_a_repeat_speaker_as_cold_start_evidence() -> None:
    client, _repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "研究")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        for message_id, text in [("repeat-1", "第一句现场经验。"), ("repeat-2", "我再补充一个约束。")]:
            websocket.send_json({
                "type": "human_message", "message_id": message_id, "participant_id": "p1",
                "text": text, "client_ts": message_id,
            })
            assert websocket.receive_json()["type"] == "message_committed"
            assert websocket.receive_json()["type"] == "table_state_changed"

        websocket.send_json({"type": "request_nudge"})
        assert websocket.receive_json() == {
            "type": "error",
            "code": "nudge_unavailable",
            "detail": "a cold-start nudge requires the latest speaker's first human turn",
        }


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
        error = websocket.receive_json()

    assert error["code"] == "unknown_participant"
    assert "unknown participant" in error["detail"]


def test_stale_socket_cannot_write_after_participant_leaves() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({"type": "participant_left", "participant_id": "p1"})
        assert websocket.receive_json()["type"] == "table_state_changed"
        version_after_leave = repository.get("table-ws").version

        websocket.send_json({
            "type": "human_message", "message_id": "stale-unsafe", "participant_id": "p1",
            "text": "我会威胁你。", "client_ts": "2026-08-31T12:04:00Z",
        })
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "invalid_event"
        assert "unknown participant" in error["detail"]
        assert repository.get("table-ws").version == version_after_leave


def test_soft_expired_socket_rejects_new_messages_with_explicit_error() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    repository.soft_expire_table("table-ws", "问题热度已下降")
    version_before = repository.get("table-ws").version

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "human_message", "message_id": "after-expiry", "participant_id": "p1",
            "text": "不应继续写入", "client_ts": "2026-08-31T12:04:00Z",
        })
        assert websocket.receive_json() == {
            "type": "error", "code": "table_soft_expired", "detail": "table is soft-expired",
        }

    assert repository.get("table-ws").version == version_before
    assert repository.turns("table-ws") == []


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


def test_request_close_returns_ordered_shared_and_personal_artifacts() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    assert client.post("/tables/table-ws/participants", json=_participant("p2", "采购")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "human_message", "message_id": "msg-close", "participant_id": "p1",
            "text": "我亲历过采购试点，预算和责任需要澄清。", "client_ts": "2026-08-31T12:05:00Z",
        })
        [websocket.receive_json() for _ in range(3)]
        websocket.send_json({"type": "request_close"})
        started = websocket.receive_json()
        artifact = websocket.receive_json()
        final_state = websocket.receive_json()
        websocket.send_json({
            "type": "human_message", "message_id": "after-close", "participant_id": "p1",
            "text": "关闭后不应继续写入。", "client_ts": "2026-08-31T12:07:00Z",
        })
        after_close = websocket.receive_json()

    assert started == {
        "type": "close_started", "table_id": "table-ws", "state_version": 4,
        "reason": "participant_requested_close",
    }
    assert artifact["type"] == "close_artifact_ready"
    assert artifact["table_id"] == artifact["shared_baseline"]["table_id"] == "table-ws"
    assert artifact["state_version"] == artifact["shared_baseline"]["state_version"] == 5
    assert artifact["personal_card"]["participant_id"] == "p1"
    assert "personal_cards" not in artifact
    assert final_state["type"] == "table_state_changed"
    assert final_state["state"]["conversation"]["closed"] is True
    assert after_close == {"type": "error", "code": "table_closed", "detail": "table is already closed"}
    assert repository.get("table-ws").phase.value == "close"


def test_request_close_for_unknown_query_participant_does_not_leak_personal_card() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=ghost") as websocket:
        websocket.send_json({"type": "request_close"})
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "unknown_participant"
    assert "unknown participant" in error["detail"]


def test_request_close_without_evidence_returns_structured_error() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({"type": "request_close"})
        assert websocket.receive_json()["type"] == "close_started"
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "close_artifact_unavailable"
    assert "evidence" in error["detail"]


def test_frontend_valley_flow_bootstraps_viewer_and_closes_with_personal_artifact() -> None:
    repository = InMemoryTableRepository()
    client = TestClient(create_app(repository))
    actors = [
        _participant("shen-zhiyao", "自由撰稿人"),
        _participant("zhou-mo", "产品经理"),
        _participant("lin-zhou", "独立开发者"),
        _participant("xu-qing", "心理咨询师"),
    ]
    created = client.post(
        "/tables",
        json={
            "table_id": "valley-learning-to-rest",
            "core_question": "为什么我们越来越不会休息？",
            "participants": actors,
        },
    )
    assert created.status_code == 201

    joined = client.post(
        "/tables/valley-learning-to-rest/participants",
        json=_participant("viewer", "第五席"),
    )
    assert joined.status_code == 200
    assert len(joined.json()["participants"]) == 5

    with client.websocket_connect(
        "/ws/tables/valley-learning-to-rest?participant_id=viewer"
    ) as websocket:
        websocket.send_json({
            "type": "human_message",
            "message_id": "valley-contract-1",
            "participant_id": "viewer",
            "text": "我正在尝试停下来，但总觉得休息会浪费时间。",
            "client_ts": 1756728000000,
        })
        committed = websocket.receive_json()
        assert committed["type"] == "message_committed"
        assert committed["message"]["participant_id"] == "viewer"
        while True:
            state_event = websocket.receive_json()
            if state_event["type"] == "table_state_changed":
                break

        websocket.send_json({"type": "request_close"})
        started = websocket.receive_json()
        artifact = websocket.receive_json()
        closed = websocket.receive_json()

    assert started["type"] == "close_started"
    assert artifact["type"] == "close_artifact_ready"
    assert artifact["shared_baseline"]["core_question_before"] == "为什么我们越来越不会休息？"
    assert artifact["personal_card"]["participant_id"] == "viewer"
    assert closed["type"] == "table_state_changed"
    assert closed["state"]["conversation"]["closed"] is True


def test_demo_grounding_card_is_emitted_only_for_a_ground_action() -> None:
    client, repository = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200
    repository.set_trusted_grounding_card("table-ws", GroundingCard(
        title="采购流程研究", excerpt="试点与正式采购由不同责任链承接。",
        source_ref="demo:zhihu:answer:42",
    ))
    decision = (GateDecision(should_speak=True, evidence_turns=[1], reasons_to_speak=["test ground"], confidence=.9),
                RouteDecision(action=Action.GROUND, evidence_turns=[1], confidence=.9))

    with patch("app.api.websocket.decide_intervention", return_value=decision):
        with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
            websocket.send_json({
                "type": "grounding_card",
                "card": {
                    "title": "伪造标题", "excerpt": "伪造摘要", "source_ref": "fake:source",
                },
            })
            assert websocket.receive_json()["code"] == "unknown_event"
            websocket.send_json({
                "type": "human_message", "message_id": "msg-ground", "participant_id": "p1",
                "text": "这个事实需要核对。", "client_ts": "2026-08-31T12:06:00Z",
            })
            assert websocket.receive_json()["type"] == "message_committed"
            action = websocket.receive_json()
            card = websocket.receive_json()
            assert websocket.receive_json()["type"] == "table_state_changed"

    assert action["action"] == "GROUND"
    assert card == {
        "type": "grounding_card", "table_id": "table-ws", "state_version": action["state_version"],
        "title": "采购流程研究", "excerpt": "试点与正式采购由不同责任链承接。",
        "source_ref": "demo:zhihu:answer:42",
    }


def test_client_grounding_card_is_unknown_even_when_its_source_is_empty() -> None:
    client, _ = _client_with_table()
    assert client.post("/tables/table-ws/participants", json=_participant("p1")).status_code == 200

    with client.websocket_connect("/ws/tables/table-ws?participant_id=p1") as websocket:
        websocket.send_json({
            "type": "grounding_card",
            "card": {"title": "标题", "excerpt": "摘要", "source_ref": ""},
        })
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "unknown_event"
