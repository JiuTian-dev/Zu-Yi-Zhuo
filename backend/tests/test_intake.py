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
    assert payload["candidates"][0]["available_seats"] == 3
    assert payload["candidates"][0]["lobby"]["table_id"] == "agent-table"
    assert payload["candidates"][0]["lobby"]["members"] == [
        {"participant_id": "p1", "display_name": "p1", "role": "产品"},
        {"participant_id": "p2", "display_name": "p2", "role": "采购"},
    ]
    assert "participants" not in payload["candidates"][0]
    assert "declared_position" not in response.text
    assert "conversation" not in response.text
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


def test_active_intent_does_not_recommend_full_tables() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "full-table",
        "AI Agent 进入企业后，技术还是采购更容易卡住？",
        [_seed(f"p{index}", "角色") for index in range(5)],
    )
    client = TestClient(create_app(repository))
    response = client.post("/intents/preview", json={
        "message": "我想找人聊企业 Agent 的采购预算",
    })

    assert response.status_code == 200
    assert response.json()["route"] == "new_table"
    assert response.json()["candidates"] == []


def test_active_intent_does_not_match_on_generic_experience_phrasing() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "ai-table",
        "为什么 AI 产品试点总停在演示阶段？",
        [_seed("p1", "产品")],
    )
    client = TestClient(create_app(repository))

    response = client.post("/intents/preview", json={
        "message": "我想找做过线下社区养老的人，讨论独居老人如何建立互助关系",
    })

    assert response.status_code == 200
    assert response.json()["route"] == "new_table"
    assert response.json()["candidates"] == []


def test_active_intent_candidate_carries_public_origin_signal_ids() -> None:
    repository = InMemoryTableRepository()
    participant = _seed("p1", "产品").model_copy(update={"public_signal_ids": ["signal-1"]})
    repository.create(
        "signal-table",
        "企业 Agent 的采购责任如何落地？",
        [participant],
        origin_signal_ids=["signal-1"],
    )
    client = TestClient(create_app(repository))

    response = client.post("/intents/preview", json={
        "message": "我想找人聊企业 Agent 的采购责任",
    })

    assert response.status_code == 200
    assert response.json()["route"] == "join_existing"
    assert response.json()["candidates"][0]["origin_signal_ids"] == ["signal-1"]
    assert "source_ref" not in response.text


def test_active_intent_lobby_projection_does_not_leak_private_fields() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "private-check",
        "企业 Agent 的采购责任如何落地？",
        [_seed("p1", "产品")],
    )
    client = TestClient(create_app(repository))

    response = client.post("/intents/preview", json={
        "message": "我想找人聊企业 Agent 的采购责任",
    })

    assert response.status_code == 200
    lobby = response.json()["candidates"][0]["lobby"]
    assert lobby["participant_count"] == 1
    assert lobby["available_seats"] == 4
    assert "declared_position" not in response.text
    assert "relevant_experience" not in response.text
    assert "messages" not in response.text
