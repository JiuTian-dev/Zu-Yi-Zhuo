import json

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed, ValueFeedback


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="公开立场",
    )


def _closed_client(repository: InMemoryTableRepository | None = None) -> tuple[TestClient, InMemoryTableRepository]:
    repo = repository or InMemoryTableRepository()
    repo.create("feedback-table", "如何把一次讨论变成行动？", [_seed("p1"), _seed("p2")])
    repo.close_table("feedback-table")
    return TestClient(create_app(repo)), repo


def _feedback_payload(**overrides) -> dict:
    payload = {
        "cognitive_value": 5,
        "relationship_value": 4,
        "action_value": 3,
        "emotional_value": 4,
        "note": "带走了一个可以验证的下一步",
        "would_join_again": True,
    }
    payload.update(overrides)
    return payload


def test_post_close_feedback_is_self_scoped_and_summary_is_anonymous() -> None:
    client, repository = _closed_client()

    submitted = client.post(
        "/tables/feedback-table/feedback?participant_id=p1",
        json=_feedback_payload(),
    )

    assert submitted.status_code == 200
    assert submitted.json()["participant_id"] == "p1"
    assert submitted.json()["state_version"] == repository.get("feedback-table").version
    assert [event.model_dump(mode="json") for event in repository.behavior_events("p1")] == [{
        "event_id": "p1:value-feedback:feedback-table",
        "participant_id": "p1",
        "event_type": "value_feedback_submitted",
        "table_id": "feedback-table",
        "state_version": 1,
        "detail": "submitted",
    }]
    summary = client.get("/tables/feedback-table/feedback?participant_id=p2")
    assert summary.status_code == 200
    assert summary.json() == {
        "table_id": "feedback-table",
        "state_version": 1,
        "eligible_participant_count": 2,
        "response_count": 1,
        "cognitive_average": 5.0,
        "relationship_average": 4.0,
        "action_average": 3.0,
        "emotional_average": 4.0,
        "would_join_again_count": 1,
    }
    assert "note" not in summary.text and "participant_id" not in summary.text


def test_feedback_can_be_updated_without_double_counting() -> None:
    client, repository = _closed_client()
    first = client.post(
        "/tables/feedback-table/feedback?participant_id=p1", json=_feedback_payload()
    )
    updated = client.post(
        "/tables/feedback-table/feedback?participant_id=p1",
        json=_feedback_payload(cognitive_value=2, would_join_again=False),
    )

    assert first.status_code == updated.status_code == 200
    assert len(repository.value_feedback("feedback-table")) == 1
    assert len(repository.behavior_events("p1")) == 1
    summary = client.get("/tables/feedback-table/feedback?participant_id=p1").json()
    assert summary["response_count"] == 1
    assert summary["cognitive_average"] == 2.0
    assert summary["would_join_again_count"] == 0


def test_feedback_requires_closed_table_membership_and_bounded_scores() -> None:
    repository = InMemoryTableRepository()
    repository.create("open-feedback", "Q", [_seed("p1")])
    client = TestClient(create_app(repository))
    assert client.post(
        "/tables/open-feedback/feedback?participant_id=p1", json=_feedback_payload()
    ).status_code == 409

    closed, _ = _closed_client()
    assert closed.post(
        "/tables/feedback-table/feedback?participant_id=ghost", json=_feedback_payload()
    ).status_code == 403
    assert closed.post(
        "/tables/feedback-table/feedback?participant_id=p1",
        json=_feedback_payload(cognitive_value=6),
    ).status_code == 422
    assert closed.get(
        "/tables/feedback-table/feedback?participant_id=ghost"
    ).status_code == 403


def test_json_repository_persists_and_reloads_value_feedback(tmp_path) -> None:
    path = tmp_path / "tables.json"
    repository = JsonTableRepository(path)
    repository.create("persist-feedback", "Q", [_seed("p1")])
    closed = repository.close_table("persist-feedback")
    saved = repository.record_value_feedback(ValueFeedback(
        table_id="persist-feedback",
        participant_id="p1",
        state_version=closed.version,
        cognitive_value=4,
        relationship_value=5,
        action_value=2,
        emotional_value=3,
        note="重启后仍能找回",
        would_join_again=True,
    ))

    reloaded = JsonTableRepository(path)

    assert reloaded.value_feedback("persist-feedback") == [saved]
    assert [event.event_type for event in reloaded.behavior_events("p1")] == [
        "value_feedback_submitted"
    ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["tables"]["persist-feedback"]["value_feedback"][0]["participant_id"] == "p1"


def test_json_repository_keeps_legacy_tables_without_feedback(tmp_path) -> None:
    path = tmp_path / "legacy.json"
    repository = JsonTableRepository(path)
    repository.create("legacy-feedback", "Q", [_seed("p1")])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tables"]["legacy-feedback"].pop("value_feedback")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    reloaded = JsonTableRepository(path)

    assert reloaded.value_feedback("legacy-feedback") == []
