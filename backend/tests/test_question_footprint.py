import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import HumanTurn, ParticipantSeed


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="公开立场",
    )


def test_question_footprint_is_self_scoped_and_excludes_open_tables() -> None:
    repository = InMemoryTableRepository()
    repository.create("footprint-open", "仍在讨论的问题", [_seed("p1")])
    repository.create("footprint-closed", "如何把经验变成行动？", [_seed("p1"), _seed("p2")])
    repository.append_turn(
        "footprint-closed",
        HumanTurn(turn_id=1, participant_id="p1", text="我有一次试点经验可以补充。"),
    )
    repository.append_turn(
        "footprint-closed",
        HumanTurn(turn_id=2, participant_id="p2", text="我从采购侧补充一条经验。"),
    )
    repository.close_table("footprint-closed")
    repository.create(
        "footprint-next",
        "下一桌：谁来把试点变成采购共识？",
        [_seed("p2")],
        origin_table_id="footprint-closed",
    )
    client = TestClient(create_app(repository))

    response = client.get(
        "/participants/p1/question-footprint?viewer_id=p1"
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["table_id"] for item in payload] == ["footprint-closed"]
    assert payload[0]["core_question"] == "如何把经验变成行动？"
    assert payload[0]["your_contribution"] == [{
        "text": "我有一次试点经验可以补充。",
        "evidence_turns": [1],
    }]
    assert payload[0]["what_changed"] == [{
        "text": "我有一次试点经验可以补充。",
        "evidence_turns": [1],
    }, {
        "text": "我从采购侧补充一条经验。",
        "evidence_turns": [2],
    }]
    assert payload[0]["next_tables"] == [{
        "table_id": "footprint-next",
        "state_version": 0,
        "core_question": "下一桌：谁来把试点变成采购共识？",
        "phase": "opening",
        "closed": False,
    }]
    assert "declared_position" not in response.text
    assert "participant_id" not in response.text
    assert client.get(
        "/participants/p1/question-footprint?viewer_id=p2"
    ).status_code == 403


def test_question_footprint_is_bounded_and_survives_json_restart(tmp_path) -> None:
    path = tmp_path / "tables.json"
    repository = JsonTableRepository(path)
    repository.create("footprint-json", "Q", [_seed("p1")])
    repository.append_turn(
        "footprint-json",
        HumanTurn(turn_id=1, participant_id="p1", text="我有一个案例经验。"),
    )
    repository.close_table("footprint-json")
    repository.create(
        "footprint-json-next",
        "从案例到行动",
        [_seed("p2")],
        origin_table_id="footprint-json",
    )
    client = TestClient(create_app(JsonTableRepository(path)))

    response = client.get(
        "/participants/p1/question-footprint?viewer_id=p1&limit=1"
    )

    assert response.status_code == 200
    assert response.json()[0]["table_id"] == "footprint-json"
    assert response.json()[0]["next_tables"][0]["table_id"] == "footprint-json-next"
    assert client.get(
        "/participants/p1/question-footprint?viewer_id=p1&limit=51"
    ).status_code == 422
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "question_footprint" not in payload


def test_question_footprint_next_tables_are_sorted_and_bounded() -> None:
    repository = InMemoryTableRepository()
    repository.create("footprint-root", "根问题", [_seed("p1")])
    repository.append_turn(
        "footprint-root",
        HumanTurn(turn_id=1, participant_id="p1", text="我补充一个关键视角。"),
    )
    repository.close_table("footprint-root")
    for child_id in ("footprint-child-c", "footprint-child-a", "footprint-child-d", "footprint-child-b"):
        repository.create(
            child_id,
            f"问题 {child_id[-1]}",
            [_seed(child_id)],
            origin_table_id="footprint-root",
        )

    entries = repository.question_footprint("p1")

    assert [item.table_id for item in entries[0].next_tables] == [
        "footprint-child-a",
        "footprint-child-b",
        "footprint-child-c",
    ]
