from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import ParticipantSeed


def _seed(participant_id: str, role: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=f"{participant_id} 展示名",
        role=role,
        declared_position=f"{participant_id} 的私有立场",
        relevant_experience=[
            {"text": f"{participant_id} 的私有经历", "source_ref": f"private:{participant_id}"}
        ],
        public_signal_ids=[f"signal:{participant_id}"],
    )


def test_lobby_preview_answers_the_three_pre_entry_questions_without_private_fields() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "lobby",
        "AI Agent 进入企业后，技术还是采购更容易卡住？",
        [_seed("p1", "产品"), _seed("p2", "研究")],
        origin_signal_ids=["signal:p1"],
    )
    client = TestClient(create_app(repository))

    response = client.get("/tables/lobby/lobby")

    assert response.status_code == 200
    payload = response.json()
    assert payload["table_id"] == "lobby"
    assert payload["core_question"].startswith("AI Agent")
    assert payload["phase"] == "opening"
    assert payload["mode"] == "async"
    assert payload["status"] == "open"
    assert payload["state_version"] == 0
    assert payload["participant_count"] == 2
    assert payload["available_seats"] == 3
    assert payload["members"] == [
        {"participant_id": "p1", "display_name": "p1 展示名", "role": "产品"},
        {"participant_id": "p2", "display_name": "p2 展示名", "role": "研究"},
    ]
    assert payload["role_gaps"] == ["实践者"]
    assert payload["missing_perspective"] == "这一桌还缺：实践者视角。"
    assert payload["origin_signal_ids"] == ["signal:p1"]
    assert "declared_position" not in response.text
    assert "私有经历" not in response.text
    assert "conversation" not in payload
    assert repository.get("lobby").version == 0


def test_lobby_preview_reflects_progress_and_soft_expiry_without_writing() -> None:
    repository = InMemoryTableRepository()
    repository.create("lobby", "Q", [_seed("p1", "实践者")])
    repository.append_message_once("lobby", "p1", "我亲历过一次试点。", "lobby-1")
    repository.soft_expire_table("lobby", "问题热度已下降")
    client = TestClient(create_app(repository))

    response = client.get("/tables/lobby/lobby")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "soft_expired"
    assert payload["state_version"] == 2
    assert payload["current_subquestion"] == repository.get("lobby").current_subquestion
    assert repository.get("lobby").version == 2


def test_lobby_preview_uses_capacity_message_when_a_balanced_table_is_full() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "full-lobby",
        "Q",
        [_seed("p1", "产品"), _seed("p2", "研究"), _seed("p3", "实践者"),
         _seed("p4", "运营"), _seed("p5", "架构")],
    )
    client = TestClient(create_app(repository))

    payload = client.get("/tables/full-lobby/lobby").json()

    assert payload["participant_count"] == 5
    assert payload["available_seats"] == 0
    assert payload["role_gaps"] == []
    assert payload["missing_perspective"] == "这桌已坐满，暂不再补入新的视角。"


def test_lobby_preview_returns_not_found_for_unknown_table() -> None:
    client = TestClient(create_app())

    response = client.get("/tables/missing/lobby")

    assert response.status_code == 404
