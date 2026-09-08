from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed


def _participant(participant_id: str, role: str) -> dict:
    return {
        "participant_id": participant_id,
        "display_name": participant_id,
        "role": role,
        "declared_position": f"{role}的真实经历",
        "relevant_experience": [],
    }


def test_table_flow_replays_summary_and_applies_feedback() -> None:
    repository = InMemoryTableRepository()
    repository.create("e2e-table", "如何让试点真正落地？", [
        ParticipantSeed(participant_id="p1", display_name="甲", role="产品", declared_position="先试点"),
        ParticipantSeed(participant_id="p2", display_name="乙", role="采购", declared_position="先审计"),
    ])
    client = TestClient(create_app(repository))
    with client.websocket_connect("/ws/tables/e2e-table?participant_id=p1") as socket:
        socket.send_json({
            "type": "human_message", "message_id": "e2e-message", "participant_id": "p1",
            "text": "我先讲一个试点失败的真实案例。", "client_ts": 1,
        })
        assert socket.receive_json()["type"] == "message_committed"
        # Deterministic host path may stay silent; the state snapshot is the
        # authoritative boundary either way.
        first_follow_up = socket.receive_json()
        if first_follow_up["type"] != "table_state_changed":
            assert first_follow_up["type"] == "agent_action"
            assert socket.receive_json()["type"] == "table_state_changed"

        socket.send_json({"type": "request_stage_summary", "request_id": "summary-request-1"})
        requested = socket.receive_json()
        assert requested["type"] == "stage_summary_requested"
        assert requested["request_id"] == "summary-request-1"
        events = []
        while "stage_summary_published" not in [event.get("type") for event in events]:
            events.append(socket.receive_json())
        published = next(event for event in events if event["type"] == "stage_summary_published")
        summary = published["summary"]
        assert summary["table_id"] == "e2e-table"
        assert summary["revision"] == 1

        response = client.post(
            f"/tables/e2e-table/stage-summaries/{summary['summary_id']}/feedback",
            params={"participant_id": "p1", "summary_revision": 1},
            json={"kind": "missing_point", "note": "补充失败条件", "evidence_turns": [1]},
        )
        assert response.status_code == 201
        assert response.json()["status"] == "applied"

    replay = client.get("/tables/e2e-table/replay").json()
    assert len(replay["stage_summaries"]) == 2
    assert replay["stage_summaries"][-1]["revision"] == 2
    assert replay["summary_feedback"] == []
    private_replay = client.get("/tables/e2e-table/replay", params={"participant_id": "p1"}).json()
    assert private_replay["summary_feedback"][0]["participant_id"] == "p1"
