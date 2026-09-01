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


def test_lobby_discovery_returns_bounded_stable_public_cards() -> None:
    repository = InMemoryTableRepository()
    repository.create("z-open", "Z 题目", [_seed("p1", "产品")])
    repository.create("a-open", "A 题目", [_seed("p2", "研究")])
    repository.create("closed", "已结束题目", [_seed("p3", "实践者")])
    repository.create("soft", "已暂停题目", [_seed("p4", "产品")])
    repository.soft_expire_table("soft", "暂时没有新证据")
    repository.close_table("closed")
    client = TestClient(create_app(repository))

    response = client.get("/tables/discovery")

    assert response.status_code == 200
    payload = response.json()
    assert [item["table_id"] for item in payload] == ["a-open", "z-open"]
    assert payload[0]["participant_count"] == 1
    assert payload[0]["available_seats"] == 4
    assert payload[0]["members"] == [
        {"participant_id": "p2", "display_name": "p2 展示名", "role": "研究"},
    ]
    assert "私有立场" not in response.text
    assert "私有经历" not in response.text
    assert "conversation" not in response.text

    limited = client.get("/tables/discovery?limit=1")
    assert limited.status_code == 200
    assert [item["table_id"] for item in limited.json()] == ["a-open"]
    assert client.get("/tables/discovery?limit=21").status_code == 422


def test_lobby_fit_preview_explains_role_gap_without_persisting_private_profile() -> None:
    repository = InMemoryTableRepository()
    repository.create("lobby", "Q", [_seed("p1", "产品"), _seed("p2", "研究")])
    client = TestClient(create_app(repository))
    candidate = _seed("candidate", "实践者")

    response = client.post(
        "/tables/lobby/lobby-fit?participant_id=candidate",
        json=candidate.model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "table_id": "lobby",
        "participant_id": "candidate",
        "eligible": True,
        "matched_role_gap": "实践者",
        "reason": "这一桌缺少实践者视角，你的实践者可以补上这块经验。",
    }
    assert "私有" not in response.text
    assert repository.join_requests("lobby") == []
    assert repository.get("lobby").version == 0


def test_lobby_fit_preview_returns_ineligible_reasons_for_boundaries() -> None:
    repository = InMemoryTableRepository()
    repository.create("lobby", "Q", [_seed("p1", "产品")])
    client = TestClient(create_app(repository))
    candidate = _seed("candidate", "实践者")

    none_response = client.post(
        "/tables/lobby/lobby-fit?participant_id=candidate",
        json={**candidate.model_dump(mode="json"), "roundtable_invite_preference": "none"},
    )
    assert none_response.json()["eligible"] is False
    assert none_response.json()["matched_role_gap"] is None
    assert "不接收圆桌邀请" in none_response.json()["reason"]

    repository.set_no_match("p1", "candidate")
    blocked_response = client.post(
        "/tables/lobby/lobby-fit?participant_id=candidate",
        json=candidate.model_dump(mode="json"),
    )
    assert blocked_response.json() == {
        "table_id": "lobby",
        "participant_id": "candidate",
        "eligible": False,
        "matched_role_gap": None,
        "reason": "当前匹配偏好不适合这张桌。",
    }


def test_lobby_fit_preview_rejects_identity_mismatch_and_handles_full_or_closed_tables() -> None:
    repository = InMemoryTableRepository()
    repository.create("lobby", "Q", [_seed("p1", "产品")])
    client = TestClient(create_app(repository))
    candidate = _seed("candidate", "实践者")

    mismatch = client.post(
        "/tables/lobby/lobby-fit?participant_id=other",
        json=candidate.model_dump(mode="json"),
    )
    assert mismatch.status_code == 403

    full_repository = InMemoryTableRepository()
    full_repository.create(
        "full",
        "Q",
        [_seed("p1", "产品"), _seed("p2", "研究"), _seed("p3", "实践者"),
         _seed("p4", "运营"), _seed("p5", "架构")],
    )
    full_client = TestClient(create_app(full_repository))
    full = full_client.post(
        "/tables/full/lobby-fit?participant_id=candidate",
        json=candidate.model_dump(mode="json"),
    )
    assert full.json()["eligible"] is False
    assert "坐满" in full.json()["reason"]

    repository.close_table("lobby")
    closed = client.post(
        "/tables/lobby/lobby-fit?participant_id=candidate",
        json=candidate.model_dump(mode="json"),
    )
    assert closed.json()["eligible"] is False
    assert "已经结束" in closed.json()["reason"]
