from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.comment_curation import (
    MAX_COMMENT_CURATION_INPUTS,
    build_comment_promotion_candidates,
)
from app.domain import CommentPromotion, ParticipantSeed, PeripheralComment
from app.orchestrator import enforce_safety, evaluate_safety


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="公开立场",
    )


def _comment(
    table_id: str,
    comment_id: str,
    text: str,
    *,
    state_version: int = 0,
) -> PeripheralComment:
    return PeripheralComment(
        comment_id=comment_id,
        table_id=table_id,
        author_id=f"author-{comment_id}",
        display_name=f"旁听者-{comment_id}",
        text=text,
        state_version=state_version,
    )


def _identity(request) -> str | None:
    return request.headers.get("x-user-id")


def test_comment_candidates_rank_relevant_questions_without_scores_or_mutation() -> None:
    repository = InMemoryTableRepository()
    state = repository.create(
        "curation",
        "AI Agent 如何进入企业采购？",
        [_seed("p1"), _seed("p2")],
    )
    comments = [
        _comment("curation", "generic", "说得不错，继续聊。"),
        _comment("curation", "question", "企业采购为什么会卡在安全评估？"),
        _comment("curation", "case", "企业采购卡点有没有具体实践案例和数据？"),
        _comment("curation", "unsafe", "企业采购不听我的就威胁他们。"),
        _comment("curation", "promoted", "企业采购有没有亲历案例？"),
    ]
    promotion = CommentPromotion(
        promotion_id="already-promoted",
        table_id="curation",
        comment_id="promoted",
        promoter_id="p1",
        turn_id=1,
        state_version=0,
        message_id="promoted-message",
    )

    result = build_comment_promotion_candidates(
        state,
        comments,
        [promotion],
        limit=5,
    )

    assert [item.comment.comment_id for item in result.items] == ["case", "question"]
    assert result.items[0].signals == ["topic_match", "question", "experience"]
    assert "采购" in result.items[0].matched_topics
    assert "案例" in result.items[0].reason
    assert result.model_dump(mode="json").get("score") is None
    assert "score" not in result.model_dump_json()
    assert repository.get("curation") == state
    assert repository.safety_strike_count("curation", "author-unsafe") == 0


def test_comment_candidates_only_consider_latest_bounded_public_comments() -> None:
    repository = InMemoryTableRepository()
    state = repository.create("bounded", "企业采购如何落地？", [_seed("p1")])
    comments = [
        _comment("bounded", "too-old", "企业采购有没有具体实践案例？"),
        *[
            _comment("bounded", f"generic-{index:03d}", "收到")
            for index in range(MAX_COMMENT_CURATION_INPUTS - 1)
        ],
        _comment("bounded", "latest", "企业采购为什么缺少真实案例？"),
    ]

    result = build_comment_promotion_candidates(state, comments, [], limit=10)

    assert result.total == 1
    assert [item.comment.comment_id for item in result.items] == ["latest"]


def test_comment_candidate_endpoint_is_member_scoped_and_read_only() -> None:
    repository = InMemoryTableRepository()
    repository.create("member-only", "社区项目如何真正落地？", [_seed("p1")])
    repository.append_comment_once(
        _comment("member-only", "candidate", "社区项目有没有具体落地案例？")
    )
    client = TestClient(create_app(repository, identity_resolver=_identity))

    assert client.get(
        "/tables/member-only/comment-promotion-candidates?participant_id=p1"
    ).status_code == 401
    assert client.get(
        "/tables/member-only/comment-promotion-candidates?participant_id=p1",
        headers={"X-User-ID": "other"},
    ).status_code == 403
    assert client.get(
        "/tables/member-only/comment-promotion-candidates?participant_id=outsider",
        headers={"X-User-ID": "outsider"},
    ).status_code == 403
    valid = client.get(
        "/tables/member-only/comment-promotion-candidates?participant_id=p1",
        headers={"X-User-ID": "p1"},
    )

    assert valid.status_code == 200
    assert valid.json()["state_version"] == 0
    assert valid.json()["items"][0]["comment"]["comment_id"] == "candidate"
    assert repository.get("member-only").version == 0
    assert repository.comment_promotions("member-only") == []
    assert client.get(
        "/tables/member-only/comment-promotion-candidates?participant_id=p1&limit=11",
        headers={"X-User-ID": "p1"},
    ).status_code == 422

    promoted = client.post(
        "/tables/member-only/comments/candidate/promote?participant_id=p1",
        headers={"X-User-ID": "p1"},
    )
    after = client.get(
        "/tables/member-only/comment-promotion-candidates?participant_id=p1",
        headers={"X-User-ID": "p1"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["promotion"]["comment_id"] == "candidate"
    assert after.json()["items"] == []


def test_comment_candidate_endpoint_rejects_inactive_or_paused_tables() -> None:
    repositories: list[tuple[InMemoryTableRepository, str]] = []

    closed = InMemoryTableRepository()
    closed.create("closed", "Q", [_seed("p1")])
    closed.close_table("closed")
    repositories.append((closed, "closed"))

    soft = InMemoryTableRepository()
    soft.create("soft", "Q", [_seed("p1")])
    soft.soft_expire_table("soft", "暂时没有新参与")
    repositories.append((soft, "soft"))

    paused = InMemoryTableRepository()
    paused.create("paused", "Q", [_seed("p1")])
    paused.record_safety_strike("paused", "guest")
    paused.record_safety_strike("paused", "guest")
    decision = evaluate_safety("我要威胁别人", 1)
    paused.append_safety_state("paused", enforce_safety(paused.get("paused"), decision))
    repositories.append((paused, "paused"))

    for repository, table_id in repositories:
        response = TestClient(create_app(repository)).get(
            f"/tables/{table_id}/comment-promotion-candidates?participant_id=p1"
        )
        assert response.status_code == 409
