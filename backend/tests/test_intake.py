from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed


def _seed(participant_id: str, role: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role=role,
        declared_position="公开立场",
    )


def test_active_intent_routes_to_matching_open_table_without_writing() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "agent-table",
        "AI Agent 进入企业后，技术还是采购更容易卡住？",
        [_seed("p1", "产品"), _seed("p2", "采购")],
    )
    client = TestClient(create_app(repository))

    response = client.post("/intents/preview", json={
        "message": "我想找人聊企业 Agent 的采购预算和技术落地",
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "join_existing"
    assert payload["normalized_question"] == "企业 Agent 的采购预算和技术落地"
    assert payload["candidates"][0]["table_id"] == "agent-table"
    assert payload["candidates"][0]["participant_count"] == 2
    assert "participants" not in payload["candidates"][0]
    assert [state.table_id for state in repository.list_tables()] == ["agent-table"]


def test_active_intent_clarifies_generic_request_and_routes_new_topic() -> None:
    client = TestClient(create_app())

    clarify = client.post("/intents/preview", json={"message": "找人聊"})
    assert clarify.status_code == 200
    assert clarify.json()["route"] == "clarify"
    assert clarify.json()["clarifying_question"]
    assert clarify.json()["candidates"] == []

    new_topic = client.post("/intents/preview", json={
        "message": "我想找人聊城市徒步路线和装备选择",
    })
    assert new_topic.status_code == 200
    assert new_topic.json()["route"] == "new_table"
    assert new_topic.json()["candidates"] == []


def test_active_intent_limit_is_bounded() -> None:
    client = TestClient(create_app())
    response = client.post("/intents/preview", json={
        "message": "我想找人聊企业 Agent",
        "limit": 6,
    })
    assert response.status_code == 422
