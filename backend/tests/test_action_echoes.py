import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import FollowUpOutcome, HumanTurn, ParticipantSeed


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="公开立场",
    )


def _closed_repository(repository: InMemoryTableRepository, table_id: str) -> None:
    repository.create(table_id, "如何把讨论变成行动？", [_seed("p1"), _seed("p2")])
    repository.append_turn(
        table_id,
        HumanTurn(turn_id=1, participant_id="p1", text="我会在下周整理验证清单。"),
    )
    repository.append_turn(
        table_id,
        HumanTurn(turn_id=2, participant_id="p2", text="建议先做一次小范围试点。"),
    )
    repository.append_turn(
        table_id,
        HumanTurn(turn_id=3, participant_id="p2", text="我会补充采购侧的案例经验。"),
    )
    repository.close_table(table_id)


def test_action_echoes_only_include_the_viewers_actions() -> None:
    repository = InMemoryTableRepository()
    _closed_repository(repository, "echo-table")
    repository.record_follow_up_outcome(FollowUpOutcome(
        table_id="echo-table",
        follow_up_index=0,
        participant_id="p1",
        status="completed",
        note="验证清单已经整理完成",
    ))
    repository.record_follow_up_outcome(FollowUpOutcome(
        table_id="echo-table",
        follow_up_index=1,
        participant_id="p1",
        status="in_progress",
    ))
    repository.record_follow_up_outcome(FollowUpOutcome(
        table_id="echo-table",
        follow_up_index=2,
        participant_id="p2",
        status="completed",
    ))
    client = TestClient(create_app(repository))

    response = client.get("/participants/p1/action-echoes?viewer_id=p1")

    assert response.status_code == 200
    payload = response.json()
    assert [item["follow_up_index"] for item in payload] == [0, 1]
    assert payload[0] == {
        "table_id": "echo-table",
        "state_version": 4,
        "core_question": "如何把讨论变成行动？",
        "follow_up_index": 0,
        "item_type": "commitment",
        "text": "我会在下周整理验证清单。",
        "evidence_turns": [1],
        "status": "completed",
        "note": "验证清单已经整理完成",
    }
    assert payload[1]["item_type"] == "suggestion"
    assert payload[1]["status"] == "in_progress"
    assert "participant_id" not in response.text
    assert client.get(
        "/participants/p1/action-echoes?viewer_id=p2"
    ).status_code == 403


def test_action_echoes_are_bounded_and_survive_json_restart(tmp_path) -> None:
    path = tmp_path / "tables.json"
    repository = JsonTableRepository(path)
    _closed_repository(repository, "echo-json")
    repository.record_follow_up_outcome(FollowUpOutcome(
        table_id="echo-json",
        follow_up_index=0,
        participant_id="p1",
        status="blocked",
    ))
    client = TestClient(create_app(JsonTableRepository(path)))

    response = client.get(
        "/participants/p1/action-echoes?viewer_id=p1&limit=1"
    )

    assert response.status_code == 200
    assert response.json()[0]["status"] == "blocked"
    assert client.get(
        "/participants/p1/action-echoes?viewer_id=p1&limit=51"
    ).status_code == 422
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "action_echoes" not in payload
