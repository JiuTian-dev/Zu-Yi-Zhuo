import json

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import ParticipantSeed, PeripheralComment


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="桌内立场",
    )


def _client(repository: InMemoryTableRepository) -> TestClient:
    return TestClient(create_app(repository))


def _repository(table_id: str = "promotion-table") -> InMemoryTableRepository:
    repository = InMemoryTableRepository()
    repository.create(table_id, "如何让讨论产生行动？", [_seed("p1"), _seed("p2")])
    return repository


def _comment_payload(comment_id: str = "c1", text: str = "可以补充一个真实案例") -> dict[str, str]:
    return {"comment_id": comment_id, "display_name": "旁听者", "text": text}


def test_member_can_promote_comment_with_provenance_and_idempotency() -> None:
    repository = _repository()
    client = _client(repository)
    assert client.post(
        "/tables/promotion-table/comments?author_id=guest",
        json=_comment_payload(),
    ).status_code == 200

    assert client.post(
        "/tables/promotion-table/comments/c1/promote?participant_id=guest",
    ).status_code == 403
    first = client.post(
        "/tables/promotion-table/comments/c1/promote?participant_id=p1",
    )
    retry = client.post(
        "/tables/promotion-table/comments/c1/promote?participant_id=p1",
    )
    other = client.post(
        "/tables/promotion-table/comments/c1/promote?participant_id=p2",
    )

    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert other.status_code == 409
    body = first.json()
    assert body["promotion"]["comment_id"] == "c1"
    assert body["promotion"]["promoter_id"] == "p1"
    assert body["turn"]["participant_id"] == "p1"
    assert body["turn"]["source_comment_id"] == "c1"
    assert body["state"]["version"] == 1
    assert len(repository.turns("promotion-table")) == 1
    assert len(repository.comment_promotions("promotion-table")) == 1
    replay = client.get("/tables/promotion-table/replay").json()
    assert replay["comments"][0]["comment_id"] == "c1"
    assert replay["comment_promotions"][0]["turn_id"] == 1
    assert replay["messages"][0]["source_comment_id"] == "c1"


def test_harmful_comment_is_safety_blocked_without_core_turn() -> None:
    repository = _repository("promotion-safety")
    client = _client(repository)
    assert client.post(
        "/tables/promotion-safety/comments?author_id=guest",
        json=_comment_payload(text="我要威胁并骚扰别人"),
    ).status_code == 200

    response = client.post(
        "/tables/promotion-safety/comments/c1/promote?participant_id=p1",
    )

    assert response.status_code == 422
    assert repository.turns("promotion-safety") == []
    assert repository.comment_promotions("promotion-safety") == []
    assert repository.get("promotion-safety").version == 1
    assert repository.get("promotion-safety").conversation.state == "safety_paused"


def test_boundary_comment_needs_private_reminder_before_repeat_pause() -> None:
    repository = _repository("promotion-boundary")
    client = _client(repository)
    assert client.post(
        "/tables/promotion-boundary/comments?author_id=guest",
        json=_comment_payload(text="你先闭嘴。"),
    ).status_code == 200

    first = client.post(
        "/tables/promotion-boundary/comments/c1/promote?participant_id=p1",
    )
    second = client.post(
        "/tables/promotion-boundary/comments/c1/promote?participant_id=p1",
    )

    assert first.status_code == 409
    assert "private safety reminder" in first.json()["detail"]
    assert second.status_code == 422
    assert repository.safety_strike_count("promotion-boundary", "guest") == 2
    assert repository.get("promotion-boundary").conversation.state == "safety_paused"
    assert repository.turns("promotion-boundary") == []


def test_promotion_broadcasts_comment_and_projected_state() -> None:
    repository = _repository("promotion-broadcast")
    client = _client(repository)
    assert client.post(
        "/tables/promotion-broadcast/comments?author_id=guest",
        json=_comment_payload(),
    ).status_code == 200

    with client.websocket_connect(
        "/ws/tables/promotion-broadcast?participant_id=observer&viewer_mode=observer"
    ) as observer:
        assert observer.receive_json()["type"] == "table_state_changed"
        response = client.post(
            "/tables/promotion-broadcast/comments/c1/promote?participant_id=p1",
        )
        assert response.status_code == 200
        assert observer.receive_json()["type"] == "comment_promoted"
        assert observer.receive_json()["type"] == "table_state_changed"


def test_promotion_respects_unknown_and_closed_boundaries() -> None:
    repository = _repository("promotion-guards")
    client = _client(repository)
    assert client.post(
        "/tables/promotion-guards/comments/unknown/promote?participant_id=p1",
    ).status_code == 404
    assert client.post(
        "/tables/promotion-guards/comments?author_id=guest",
        json=_comment_payload(),
    ).status_code == 200
    repository.close_table("promotion-guards")
    assert client.post(
        "/tables/promotion-guards/comments/c1/promote?participant_id=p1",
    ).status_code == 409


def test_json_repository_persists_promoted_comment_and_accepts_legacy_tables(tmp_path) -> None:
    path = tmp_path / "tables.json"
    repository = JsonTableRepository(path)
    repository.create("persist-promotion", "Q", [_seed("p1"), _seed("p2")])
    repository.append_comment_once(PeripheralComment(
        comment_id="c1",
        table_id="persist-promotion",
        author_id="guest",
        display_name="旁听者",
        text="保留公共补充",
        state_version=0,
    ))
    promotion, state, created = repository.promote_comment_once(
        "persist-promotion", "c1", "p1", expected_state_version=0
    )
    assert created and state.version == 1

    reloaded = JsonTableRepository(path)
    assert reloaded.comment_promotions("persist-promotion") == [promotion]
    assert reloaded.turns("persist-promotion")[0].source_comment_id == "c1"

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tables"]["persist-promotion"].pop("comment_promotions")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    legacy = JsonTableRepository(path)
    assert legacy.comment_promotions("persist-promotion") == []
