import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import HumanTurn, ParticipantSeed


def _seed(participant_id: str, role: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role=role,
        declared_position="公开立场",
        relevant_experience=[],
    )


def _closed_repository(repository: InMemoryTableRepository | None = None) -> InMemoryTableRepository:
    repo = repository or InMemoryTableRepository()
    repo.create(
        "source-table",
        "AI 进入企业的最大阻力是什么？",
        [_seed("old-1", "技术"), _seed("old-2", "采购")],
    )
    repo.append_turn(
        "source-table",
        HumanTurn(turn_id=1, participant_id="old-1", text="我亲历过一次技术试点。"),
    )
    repo.append_turn(
        "source-table",
        HumanTurn(turn_id=2, participant_id="old-2", text="采购预算和责任边界需要先说清。"),
    )
    repo.close_table("source-table")
    return repo


def test_recompose_creates_next_table_from_evolved_question_without_copying_members() -> None:
    repository = _closed_repository()
    client = TestClient(create_app(repository))

    response = client.post("/tables/source-table/recompose", json={
        "table_id": "next-table",
        "participants": [
            _seed("new-1", "实践者").model_dump(mode="json"),
            _seed("new-2", "产品").model_dump(mode="json"),
        ],
    })

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_table_id"] == "source-table"
    assert payload["new_table_id"] == "next-table"
    assert payload["source_state_version"] == 3
    assert payload["evolved_question"]["evidence_turns"] == [1, 2]
    assert payload["state"]["core_question"] == payload["evolved_question"]["text"]
    assert payload["state"]["origin_table_id"] == "source-table"
    assert set(payload["state"]["participants"]) == {"new-1", "new-2"}
    assert set(repository.get("next-table").participants) == {"new-1", "new-2"}
    assert repository.get("source-table").conversation.closed is True
    assert repository.get("source-table").version == 3


def test_recompose_requires_closed_source_and_reselects_bounded_participants() -> None:
    open_repository = InMemoryTableRepository()
    open_repository.create("open-source", "Q", [_seed("p1", "产品")])
    client = TestClient(create_app(open_repository))
    valid = {
        "participants": [
            _seed("new-1", "实践者").model_dump(mode="json"),
            _seed("new-2", "产品").model_dump(mode="json"),
        ],
    }
    assert client.post("/tables/open-source/recompose", json=valid).status_code == 409

    closed_client = TestClient(create_app(_closed_repository()))
    assert closed_client.post(
        "/tables/source-table/recompose", json={"participants": [_seed("only", "实践者").model_dump(mode="json")]}
    ).status_code == 422
    assert closed_client.post(
        "/tables/source-table/recompose", json={**valid, "table_id": "next-table"}
    ).status_code == 201
    assert closed_client.post(
        "/tables/source-table/recompose", json={**valid, "table_id": "next-table"}
    ).status_code == 409


def test_json_repository_persists_origin_table_id(tmp_path) -> None:
    path = tmp_path / "tables.json"
    repository = _closed_repository(JsonTableRepository(path))
    client = TestClient(create_app(repository))
    response = client.post("/tables/source-table/recompose", json={
        "table_id": "next-persisted",
        "participants": [
            _seed("new-1", "实践者").model_dump(mode="json"),
            _seed("new-2", "产品").model_dump(mode="json"),
        ],
    })
    assert response.status_code == 201
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["tables"]["next-persisted"]["states"][0]["origin_table_id"] == "source-table"
    reloaded = JsonTableRepository(path)
    assert reloaded.get("next-persisted").origin_table_id == "source-table"
