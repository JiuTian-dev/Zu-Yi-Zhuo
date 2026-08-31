import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import BehaviorEvent, ParticipantSeed


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="桌内立场",
    )


def _repository(table_id: str = "behavior-table") -> InMemoryTableRepository:
    repository = InMemoryTableRepository()
    repository.create(table_id, "Q", [_seed("p1"), _seed("p2")])
    return repository


def test_behavior_events_are_self_scoped_bounded_and_idempotent() -> None:
    repository = _repository()
    client = TestClient(create_app(repository))
    payload = {
        "event_id": "select-1",
        "event_type": "table_selected",
        "table_id": "behavior-table",
        "detail": "从首页选择这桌",
    }
    first = client.post(
        "/participants/viewer/behavior-events?viewer_id=viewer", json=payload
    )
    retry = client.post(
        "/participants/viewer/behavior-events?viewer_id=viewer", json=payload
    )
    conflict = client.post(
        "/participants/viewer/behavior-events?viewer_id=viewer",
        json={**payload, "detail": "改写行为"},
    )
    private = client.get(
        "/participants/viewer/behavior-events?viewer_id=viewer"
    )

    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json()
    assert conflict.status_code == 409
    assert private.json() == [first.json()]
    assert client.get(
        "/participants/viewer/behavior-events?viewer_id=other"
    ).status_code == 403

    relation = client.post(
        "/participants/viewer/behavior-events?viewer_id=viewer",
        json={
            "event_id": "relation-1",
            "event_type": "relationship_saved",
            "table_id": "behavior-table",
            "related_participant_id": "p1",
        },
    )
    assert relation.status_code == 201
    assert [item["event_type"] for item in private.json()] == ["table_selected"]
    assert client.get(
        "/participants/viewer/behavior-events?viewer_id=viewer"
    ).json()[-1]["event_type"] == "relationship_saved"


def test_human_turn_automatically_creates_behavior_event() -> None:
    repository = _repository("behavior-auto")
    state, created = repository.append_message_once(
        "behavior-auto", "p1", "补一个现场", "message-1"
    )

    assert created and state.version == 1
    assert repository.behavior_events("p1")[0].model_dump(mode="json") == {
        "event_id": "message-1",
        "participant_id": "p1",
        "event_type": "human_message",
        "table_id": "behavior-auto",
        "state_version": 1,
    }


def test_json_behavior_events_persist_and_legacy_files_default_empty(tmp_path) -> None:
    path = tmp_path / "behavior.json"
    repository = JsonTableRepository(path)
    repository.create("behavior-json", "Q", [_seed("p1")])
    saved, created = repository.record_behavior_event(BehaviorEvent(
        event_id="selected",
        participant_id="p1",
        event_type="table_selected",
        table_id="behavior-json",
    ))
    assert created
    assert saved.event_id == "selected"
    assert JsonTableRepository(path).behavior_events("p1") == [saved]

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("behavior_events")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert JsonTableRepository(path).behavior_events("p1") == []
