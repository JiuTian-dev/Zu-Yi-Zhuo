from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import HumanTurn, ParticipantSeed


def client_and_repo() -> tuple[TestClient, InMemoryTableRepository]:
    repository = InMemoryTableRepository()
    return TestClient(create_app(repository)), repository


def participant(participant_id: str = "p1") -> dict[str, str]:
    return {
        "participant_id": participant_id,
        "display_name": "甲",
        "role": "产品",
        "declared_position": "先验证价值",
    }


def test_table_lifecycle_returns_serializable_snapshots_and_close_artifact() -> None:
    client, repository = client_and_repo()
    created = client.post("/tables", json={"table_id": "t-api", "core_question": "如何开始？"})
    assert created.status_code == 201 and created.json()["version"] == 0

    joined = client.post("/tables/t-api/participants", json=participant())
    assert joined.status_code == 200 and joined.json()["version"] == 1
    assert client.get("/tables/t-api/state").json() == joined.json()

    repository.append_turn("t-api", HumanTurn(turn_id=1, participant_id="p1", text="我亲历过一次试点。"))
    replay = client.get("/tables/t-api/replay")
    payload = replay.json()
    assert replay.status_code == 200 and [item["version"] for item in payload["snapshots"]] == [0, 1, 2]
    assert payload["messages"] == [{"turn_id": 1, "participant_id": "p1", "text": "我亲历过一次试点。"}]
    filtered = client.get("/tables/t-api/replay?from_version=1").json()
    assert [item["version"] for item in filtered["snapshots"]] == [1, 2]

    closed = client.post("/tables/t-api/close")
    assert closed.status_code == 200
    assert closed.json()["table_id"] == "t-api" and closed.json()["state_version"] == 2


def test_api_rejects_unknown_tables_duplicate_participants_and_empty_close() -> None:
    client, _ = client_and_repo()
    assert client.get("/tables/missing").status_code == 404
    assert client.get("/tables/missing/replay?from_version=9").status_code == 404
    assert client.post("/tables", json={"table_id": "empty", "core_question": "Q"}).status_code == 201
    assert client.post("/tables/empty/close").status_code == 409
    assert client.get("/tables/empty/replay?from_version=1").status_code == 404
    assert client.get("/tables/empty/replay?from_version=-1").status_code == 422
    assert client.post("/tables/empty/participants", json=participant()).status_code == 200
    assert client.post("/tables/empty/participants", json=participant()).status_code == 409


def test_repository_rejects_unknown_participants_and_invalid_turn_order() -> None:
    repository = InMemoryTableRepository()
    repository.create("turns", "Q", [])
    try:
        repository.append_turn("turns", HumanTurn(turn_id=1, participant_id="ghost", text="你好"))
    except ValueError as error:
        assert "unknown participant" in str(error)
    else:
        raise AssertionError("unknown participant was accepted")


def test_repository_replay_and_turns_are_isolated_from_callers() -> None:
    repository = InMemoryTableRepository()
    repository.create("copies", "Q", [ParticipantSeed.model_validate(participant())])
    repository.append_turn("copies", HumanTurn(turn_id=1, participant_id="p1", text="原始消息"))

    snapshots = repository.replay("copies")
    messages = repository.turns("copies")
    snapshots[0].core_question = "篡改后的问题"
    messages[0].text = "篡改后的消息"

    assert repository.replay("copies")[0].core_question == "Q"
    assert repository.turns("copies")[0].text == "原始消息"


def test_repository_get_is_isolated_from_callers() -> None:
    repository = InMemoryTableRepository()
    repository.create("current", "Q", [])
    state = repository.get("current")
    state.core_question = "篡改后的问题"

    assert repository.get("current").core_question == "Q"
