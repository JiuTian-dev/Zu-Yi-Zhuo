import pytest

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
    assert closed.json()["table_id"] == "t-api" and closed.json()["state_version"] == 3
    assert client.get("/tables/t-api/state").json()["conversation"]["closed"] is True
    assert client.post("/tables/t-api/close").json()["state_version"] == 3
    assert repository.get("t-api").phase.value == "close"
    with pytest.raises(ValueError, match="table is closed"):
        repository.append_turn("t-api", HumanTurn(turn_id=2, participant_id="p1", text="不应再写入"))


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


def test_profile_fields_are_hidden_until_explicit_consent() -> None:
    client, _ = client_and_repo()
    created = client.post("/tables", json={
        "table_id": "privacy",
        "core_question": "Q",
        "participants": [
            {
                **participant("p1"),
                "declared_position": "只对本人可见的立场",
                "relevant_experience": [{"text": "未公开采购经历", "source_ref": "private:1"}],
            },
            {
                **participant("p2"),
                "declared_position": "另一份私有立场",
                "relevant_experience": [{"text": "另一份经历", "source_ref": "private:2"}],
            },
        ],
    })
    assert created.status_code == 201
    assert created.json()["participants"]["p1"]["declared_position"] is None
    assert created.json()["participants"]["p1"]["unused_relevant_experience"] == []

    own_view = client.get("/tables/privacy/state?participant_id=p1").json()
    assert own_view["participants"]["p1"]["declared_position"] == "只对本人可见的立场"
    assert own_view["participants"]["p1"]["unused_relevant_experience"][0]["source_ref"] == "private:1"
    assert own_view["participants"]["p2"]["declared_position"] is None

    consented = client.post("/tables/privacy/participants/p2/consent", json={"profile_shared": True})
    assert consented.status_code == 200
    assert consented.json()["participants"]["p2"]["declared_position"] == "另一份私有立场"
    public_view = client.get("/tables/privacy/state").json()
    assert public_view["participants"]["p2"]["declared_position"] == "另一份私有立场"
    assert public_view["participants"]["p2"]["unused_relevant_experience"][0]["source_ref"] == "private:2"

    revoked = client.post("/tables/privacy/participants/p2/consent", json={"profile_shared": False})
    assert revoked.status_code == 200
    assert client.get("/tables/privacy/state").json()["participants"]["p2"]["declared_position"] is None


def test_match_preview_returns_public_seats_and_explainable_reasons() -> None:
    client, _ = client_and_repo()
    candidates = [
        {
            "participant_id": "tech",
            "display_name": "技术角色",
            "role": "AI 架构师",
            "declared_position": "模型精度是关键",
            "relevant_experience": [{"text": "做过企业 Agent 落地", "source_ref": "private:tech"}],
        },
        {
            "participant_id": "buyer",
            "display_name": "采购角色",
            "role": "企业采购负责人",
            "declared_position": "采购责任链是关键",
            "relevant_experience": [{"text": "亲历过供应商采购", "source_ref": "private:buyer"}],
        },
        {
            "participant_id": "product",
            "display_name": "产品角色",
            "role": "产品负责人",
            "declared_position": "价值闭环更重要",
        },
    ]
    response = client.post("/matches/preview", json={
        "core_question": "AI Agent 进入企业卡在哪里？",
        "candidates": candidates,
        "table_size": 3,
    })
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["selected"]) == 3
    assert {seat["participant_id"] for seat in payload["selected"]} == {"tech", "buyer", "product"}
    assert {reason["participant_id"] for reason in payload["reasons"]} == {"tech", "buyer", "product"}
    assert all("declared_position" not in seat and "relevant_experience" not in seat for seat in payload["selected"])
    serialized = response.text
    assert "模型精度是关键" not in serialized
    assert "private:tech" not in serialized


def test_match_confirm_creates_a_table_from_the_same_public_match_plan() -> None:
    client, _ = client_and_repo()
    candidates = [
        {**participant("p1"), "role": "架构师", "relevant_experience": [{"text": "做过 Agent 试点", "source_ref": "private:1"}]},
        {**participant("p2"), "role": "采购负责人", "relevant_experience": [{"text": "做过供应商采购", "source_ref": "private:2"}]},
        {**participant("p3"), "role": "产品负责人"},
    ]
    response = client.post("/matches/confirm", json={
        "table_id": "matched-table", "core_question": "Agent 试点如何进入企业？",
        "candidates": candidates, "table_size": 3,
    })
    assert response.status_code == 201
    payload = response.json()
    assert payload["plan"]["core_question"] == payload["state"]["core_question"]
    assert {seat["participant_id"] for seat in payload["plan"]["selected"]} == {"p1", "p2", "p3"}
    assert set(payload["state"]["participants"]) == {"p1", "p2", "p3"}
    assert payload["state"]["participants"]["p1"]["declared_position"] is None
    assert client.post("/matches/confirm", json={
        "table_id": "matched-table", "core_question": "Q", "candidates": candidates, "table_size": 3,
    }).status_code == 409


def test_health_and_readiness_probes_are_available() -> None:
    client = TestClient(create_app())

    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {
        "status": "ready",
        "repository": "InMemoryTableRepository",
    }


def test_default_cors_allows_vite_dev_origin() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/healthz",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
