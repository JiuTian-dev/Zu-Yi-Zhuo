import json

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import BehaviorEvent, FollowUpOutcome, HumanTurn, ParticipantSeed


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

    repository.close_table("behavior-table")
    relation = client.post(
        "/participants/p1/behavior-events?viewer_id=p1",
        json={
            "event_id": "relation-1",
            "event_type": "relationship_saved",
            "table_id": "behavior-table",
            "related_participant_id": "p2",
        },
    )
    assert relation.status_code == 201
    assert [item["event_type"] for item in private.json()] == ["table_selected"]
    assert client.get(
        "/participants/p1/behavior-events?viewer_id=p1"
    ).json()[-1]["event_type"] == "relationship_saved"


def test_behavior_event_context_rejects_non_members_and_open_table_relationships() -> None:
    repository = _repository("behavior-context")
    client = TestClient(create_app(repository))

    for event_type in ("human_message", "follow_up_outcome"):
        response = client.post(
            "/participants/outsider/behavior-events?viewer_id=outsider",
            json={
                "event_id": f"{event_type}-1",
                "event_type": event_type,
                "table_id": "behavior-context",
                "state_version": 0,
                "detail": "status:completed" if event_type == "follow_up_outcome" else None,
            },
        )
        assert response.status_code == 409

    relationship = client.post(
        "/participants/p1/behavior-events?viewer_id=p1",
        json={
            "event_id": "relationship-open",
            "event_type": "relationship_saved",
            "table_id": "behavior-context",
            "related_participant_id": "p2",
        },
    )
    assert relationship.status_code == 409


def test_server_generated_table_selection_is_open_scoped_and_idempotent() -> None:
    repository = _repository("selection-table")
    client = TestClient(create_app(repository))

    first = client.post("/tables/selection-table/select?participant_id=viewer")
    retry = client.post("/tables/selection-table/select?participant_id=viewer")

    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json() == {
        "event_id": "viewer:table-selected:selection-table",
        "participant_id": "viewer",
        "event_type": "table_selected",
        "table_id": "selection-table",
        "detail": "selected",
    }
    assert repository.get("selection-table").version == 0
    assert set(repository.get("selection-table").participants) == {"p1", "p2"}

    repository.close_table("selection-table")
    assert client.post("/tables/selection-table/select?participant_id=viewer").status_code == 409


def test_close_path_records_actor_scoped_table_closed_behavior() -> None:
    repository = _repository("close-behavior")
    client = TestClient(create_app(repository))
    repository.append_message_once(
        "close-behavior", "p1", "我愿意把这次讨论收束成下一步。", "close-1"
    )

    first = client.post("/tables/close-behavior/close?participant_id=p1")
    retry = client.post("/tables/close-behavior/close?participant_id=p1")

    assert first.status_code == retry.status_code == 200
    assert first.json()["state_version"] == retry.json()["state_version"] == 2
    assert client.get("/participants/p1/behavior-events?viewer_id=p1").json() == [{
        "event_id": "p1:table-closed:close-behavior",
        "participant_id": "p1",
        "event_type": "table_closed",
        "table_id": "close-behavior",
        "state_version": 2,
        "detail": "closed",
    }]
    assert client.get("/participants/p2/behavior-events?viewer_id=p2").json() == []


def test_relationship_save_is_closed_member_scoped_and_idempotent() -> None:
    repository = _repository("relationship-save")
    client = TestClient(create_app(repository))

    assert client.post(
        "/tables/relationship-save/relationships/p2/save?participant_id=p1"
    ).status_code == 409
    repository.append_turn(
        "relationship-save",
        HumanTurn(turn_id=1, participant_id="p1", text="我会先做一次小范围试点。"),
    )
    closed = repository.close_table("relationship-save")

    first = client.post(
        "/tables/relationship-save/relationships/p2/save?participant_id=p1"
    )
    retry = client.post(
        "/tables/relationship-save/relationships/p2/save?participant_id=p1"
    )
    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json() == {
        "event_id": "relationship-save:relationship:p1:p2",
        "participant_id": "p1",
        "event_type": "relationship_saved",
        "table_id": "relationship-save",
        "state_version": closed.version,
        "related_participant_id": "p2",
        "detail": "saved",
    }
    assert client.post(
        "/tables/relationship-save/relationships/p2/save?participant_id=outsider"
    ).status_code == 403
    assert client.post(
        "/tables/relationship-save/relationships/unknown/save?participant_id=p1"
    ).status_code == 404
    assert client.post(
        "/tables/relationship-save/relationships/p1/save?participant_id=p1"
    ).status_code == 409


def test_human_turn_automatically_creates_behavior_event() -> None:
    repository = _repository("behavior-auto")
    state, created = repository.append_message_once(
        "behavior-auto", "p1", "补一个现场", "message-1"
    )

    assert created and state.version == 1
    assert repository.behavior_events("p1")[0].model_dump(mode="json") == {
        "event_id": "behavior-auto:human:message-1",
        "participant_id": "p1",
        "event_type": "human_message",
        "table_id": "behavior-auto",
        "state_version": 1,
    }


def test_follow_up_outcome_emits_only_status_transitions() -> None:
    repository = _repository("behavior-follow-up")
    repository.append_turn(
        "behavior-follow-up",
        HumanTurn(turn_id=1, participant_id="p1", text="我会先做一次小范围试点。"),
    )
    closed = repository.close_table("behavior-follow-up")

    def report(status: str, note: str | None = None) -> None:
        repository.record_follow_up_outcome(FollowUpOutcome(
            table_id="behavior-follow-up",
            follow_up_index=0,
            participant_id="p1",
            status=status,
            note=note,
        ))

    report("completed", "第一次回报")
    report("completed", "只更新备注，不应制造画像事件")
    report("blocked", "遇到依赖")
    report("completed", "恢复推进")

    events = [item for item in repository.behavior_events("p1") if item.event_type == "follow_up_outcome"]
    assert closed.version == 2
    assert [item.detail for item in events] == [
        "status:completed", "status:blocked", "status:completed"
    ]
    assert [item.event_id for item in events] == [
        "behavior-follow-up:follow-up:0:p1:initial",
        "behavior-follow-up:follow-up:0:p1:completed-to-blocked",
        "behavior-follow-up:follow-up:0:p1:blocked-to-completed",
    ]
    assert all(item.state_version == closed.version for item in events)


def test_follow_up_behavior_deduplication_is_reporter_scoped() -> None:
    repository = _repository("behavior-follow-up-reporters")
    repository.append_turn(
        "behavior-follow-up-reporters",
        HumanTurn(turn_id=1, participant_id="p1", text="我会先做一次小范围试点。"),
    )
    repository.close_table("behavior-follow-up-reporters")
    repository.record_follow_up_outcome(FollowUpOutcome(
        table_id="behavior-follow-up-reporters",
        follow_up_index=0,
        participant_id="p1",
        status="completed",
    ))
    repository.record_follow_up_outcome(FollowUpOutcome(
        table_id="behavior-follow-up-reporters",
        follow_up_index=0,
        participant_id="p2",
        status="completed",
    ))

    assert [item.event_id for item in repository.behavior_events("p2")] == [
        "behavior-follow-up-reporters:follow-up:0:p2:initial"
    ]


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


def test_json_follow_up_outcome_and_behavior_event_commit_together(tmp_path) -> None:
    path = tmp_path / "follow-up-behavior.json"
    repository = JsonTableRepository(path)
    repository.create("follow-up-json", "Q", [_seed("p1"), _seed("p2")])
    repository.append_turn(
        "follow-up-json",
        HumanTurn(turn_id=1, participant_id="p1", text="我会先做一次小范围试点。"),
    )
    closed = repository.close_table("follow-up-json")
    outcome = FollowUpOutcome(
        table_id="follow-up-json",
        follow_up_index=0,
        participant_id="p1",
        status="in_progress",
    )

    repository.record_follow_up_outcome(outcome)
    restarted = JsonTableRepository(path)

    assert restarted.follow_up_outcomes("follow-up-json") == [outcome]
    assert [event.model_dump(mode="json") for event in restarted.behavior_events("p1")][-1] == {
        "event_id": "follow-up-json:follow-up:0:p1:initial",
        "participant_id": "p1",
        "event_type": "follow_up_outcome",
        "table_id": "follow-up-json",
        "state_version": closed.version,
        "detail": "status:in_progress",
    }


def test_json_rejects_behavior_event_with_incompatible_table_context(tmp_path) -> None:
    path = tmp_path / "invalid-behavior-context.json"
    repository = JsonTableRepository(path)
    repository.create("context-json", "Q", [_seed("p1")])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["behavior_events"] = {
        "outsider": [{
            "event_id": "forged-human",
            "participant_id": "outsider",
            "event_type": "human_message",
            "table_id": "context-json",
            "state_version": 0,
        }]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="behavior event context"):
        JsonTableRepository(path)


def test_behavior_ledger_erasure_is_self_scoped_and_preserves_table_facts(tmp_path) -> None:
    path = tmp_path / "erase-behavior.json"
    repository = JsonTableRepository(path)
    repository.create("erase-table", "Q", [_seed("p1"), _seed("p2")])
    client = TestClient(create_app(repository))

    selected = client.post("/tables/erase-table/select?participant_id=p1")
    assert selected.status_code == 201
    assert client.post("/tables/erase-table/select?participant_id=p2").status_code == 201
    repository.append_turn(
        "erase-table",
        HumanTurn(turn_id=1, participant_id="p1", text="事实消息仍需保留。"),
    )
    version = repository.get("erase-table").version

    assert client.delete(
        "/participants/p1/behavior-events?viewer_id=other"
    ).status_code == 403
    assert client.delete(
        "/participants/p1/behavior-events?viewer_id=p1"
    ).status_code == 204
    assert client.delete(
        "/participants/p1/behavior-events?viewer_id=p1"
    ).status_code == 204

    assert client.get(
        "/participants/p1/behavior-events?viewer_id=p1"
    ).json() == []
    assert len(client.get(
        "/participants/p2/behavior-events?viewer_id=p2"
    ).json()) == 1
    assert repository.get("erase-table").version == version
    assert len(repository.turns("erase-table")) == 1
    assert JsonTableRepository(path).behavior_events("p1") == []
