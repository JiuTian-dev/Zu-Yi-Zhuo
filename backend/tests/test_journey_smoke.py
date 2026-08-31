from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import JsonTableRepository


def _signal(signal_id: str, author_id: str, role: str) -> dict[str, object]:
    return {
        "signal_id": signal_id,
        "content_type": "answer",
        "title": "企业 Agent 如何落地？",
        "excerpt": "试点需要明确责任和验收边界。",
        "source_ref": f"zhihu:public:{signal_id}",
        "author_id": author_id,
        "author_name": author_id,
        "author_role": role,
        "public_stance": "先验证价值",
    }


def _receive_until(websocket, event_type: str) -> dict:
    while True:
        event = websocket.receive_json()
        if event["type"] == event_type:
            return event


def test_product_journey_survives_json_restart(tmp_path) -> None:
    repository = JsonTableRepository(tmp_path / "journey.json")
    client = TestClient(create_app(repository))

    opportunity = client.post("/opportunities/preview", json={
        "query": "企业 Agent 真正进入企业，卡住的是技术还是采购？",
        "signals": [
            _signal("s1", "architect", "架构师"),
            _signal("s2", "operator", "实践者"),
            _signal("s3", "product", "产品经理"),
        ],
    })
    assert opportunity.status_code == 200
    candidates = opportunity.json()["candidates"]

    matched = client.post("/matches/confirm", json={
        "table_id": "journey",
        "core_question": opportunity.json()["core_question"],
        "candidates": candidates,
        "table_size": 2,
    })
    assert matched.status_code == 201
    selected = [seat["participant_id"] for seat in matched.json()["plan"]["selected"]]
    actor, other = selected
    candidate_by_id = {item["participant_id"]: item for item in candidates}
    waiting = next(
        participant_id
        for participant_id in candidate_by_id
        if participant_id not in selected
    )

    selected_event = client.post(
        "/tables/journey/select?participant_id=browser-viewer"
    )
    assert selected_event.status_code == 201
    assert selected_event.json()["event_type"] == "table_selected"

    invitation = client.post(
        "/tables/journey/invitations?inviter_id=" + actor,
        json={"candidate": candidate_by_id[waiting], "reason": "补充实践视角"},
    )
    assert invitation.status_code == 201
    invitation_id = invitation.json()["invitation_id"]
    assert client.get(
        f"/tables/journey/invitations?participant_id={waiting}"
    ).json()[0]["status"] == "pending"
    accepted = client.post(
        f"/tables/journey/invitations/{invitation_id}/respond?participant_id={waiting}",
        json={"accept": True},
    )
    assert accepted.status_code == 200
    assert waiting in accepted.json()["state"]["participants"]

    with client.websocket_connect(
        f"/ws/tables/journey?participant_id={actor}"
    ) as websocket:
        websocket.send_json({
            "type": "human_message",
            "message_id": "journey-message-1",
            "participant_id": actor,
            "text": "我会先做一次小范围试点，验证责任和验收边界。",
            "client_ts": 1756728000000,
        })
        assert websocket.receive_json()["type"] == "message_committed"
        _receive_until(websocket, "table_state_changed")

        websocket.send_json({"type": "request_close"})
        assert websocket.receive_json()["type"] == "close_started"
        artifact = websocket.receive_json()
        closed = websocket.receive_json()

    assert artifact["type"] == "close_artifact_ready"
    assert artifact["personal_card"]["participant_id"] == actor
    assert closed["type"] == "table_state_changed"
    assert closed["state"]["conversation"]["closed"] is True

    follow_ups = client.get(f"/tables/journey/follow-ups?participant_id={actor}")
    assert follow_ups.status_code == 200
    assert follow_ups.json()
    outcome = client.post(
        f"/tables/journey/follow-ups/{follow_ups.json()[0]['follow_up_index']}/outcome?participant_id={actor}",
        json={"status": "completed", "note": "已完成第一轮验证"},
    )
    assert outcome.status_code == 200

    relationship = client.post(
        f"/tables/journey/relationships/{other}/save?participant_id={actor}"
    )
    assert relationship.status_code == 201
    assert relationship.json()["event_type"] == "relationship_saved"

    feedback = client.post(
        f"/tables/journey/feedback?participant_id={actor}",
        json={
            "cognitive_value": 5,
            "relationship_value": 4,
            "action_value": 5,
            "emotional_value": 4,
            "would_join_again": True,
        },
    )
    assert feedback.status_code == 200
    summary = client.get(f"/tables/journey/feedback?participant_id={actor}")
    assert summary.status_code == 200
    assert summary.json()["response_count"] == 1

    events = client.get(f"/participants/{actor}/behavior-events?viewer_id={actor}")
    assert events.status_code == 200
    assert {event["event_type"] for event in events.json()} == {
        "human_message",
        "table_closed",
        "follow_up_outcome",
        "relationship_saved",
        "value_feedback_submitted",
    }

    restarted = JsonTableRepository(tmp_path / "journey.json")
    recovered = TestClient(create_app(restarted))
    state = recovered.get(f"/tables/journey/state?participant_id={actor}")
    assert state.status_code == 200
    assert state.json()["conversation"]["closed"] is True
    assert recovered.get(
        f"/tables/journey/close-artifacts?participant_id={actor}"
    ).status_code == 200
    assert recovered.get(
        f"/tables/journey/follow-ups?participant_id={actor}"
    ).json()[0]["outcome"]["status"] == "completed"
    assert recovered.get(
        f"/tables/journey/feedback?participant_id={actor}"
    ).json()["response_count"] == 1
    recovered_events = recovered.get(
        f"/participants/{actor}/behavior-events?viewer_id={actor}"
    ).json()
    assert {event["event_type"] for event in recovered_events} == {
        "human_message",
        "table_closed",
        "follow_up_outcome",
        "relationship_saved",
        "value_feedback_submitted",
    }
