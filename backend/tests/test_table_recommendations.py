from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository, JsonTableRepository
from app.domain import BehaviorEvent, HumanTurn, ParticipantSeed
from app.recommendations import build_personalized_table_recommendations


def _seed(participant_id: str, role: str = "讨论参与者") -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role=role,
        declared_position="公开立场",
    )


def _members(prefix: str, count: int, *, roles: list[str] | None = None) -> list[ParticipantSeed]:
    labels = roles or ["产品负责人", "研究员", "运营实践者", "桥梁者", "观察者"]
    return [_seed(f"{prefix}-{index}", labels[index]) for index in range(count)]


def _header_identity(request) -> str | None:
    return request.headers.get("x-user-id")


def test_cold_start_recommendations_are_stable_and_filter_ineligible_tables() -> None:
    repository = InMemoryTableRepository()
    repository.create("ready", "如何让 AI 进入企业？", _members("ready", 4))
    repository.create("early", "如何形成更好的休息习惯？", _members("early", 2))
    repository.create("own", "本人已经在这桌", [_seed("viewer"), *_members("own", 2)])
    repository.create("full", "满桌", _members("full", 5))
    repository.create("closed", "已关闭", _members("closed", 3))
    repository.close_table("closed")
    repository.create("expired", "已过期", _members("expired", 3))
    repository.soft_expire_table("expired", "问题热度下降")
    repository.create("blocked", "不再匹配", [_seed("blocked-member"), *_members("blocked", 2)])
    repository.set_no_match("viewer", "blocked-member")
    client = TestClient(create_app(repository))

    response = client.get(
        "/participants/viewer/table-recommendations?viewer_id=viewer"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["personalized"] is False
    assert payload["signal_count"] == 0
    assert payload["signal_types"] == []
    assert [item["table_id"] for item in payload["items"]] == ["ready", "early"]
    assert all(item["lobby"]["status"] == "open" for item in payload["items"])
    assert all("based_on_table_id" not in item for item in payload["items"])
    assert repository.get("ready").version == 0


def test_explicit_table_selection_personalizes_topic_ranking_and_explanation() -> None:
    repository = InMemoryTableRepository()
    repository.create("history", "AI Agent 进入企业为何卡在采购？", _members("history", 2))
    repository.record_behavior_event(BehaviorEvent(
        event_id="selected-history",
        participant_id="viewer",
        event_type="table_selected",
        table_id="history",
        detail="selected",
    ))
    repository.close_table("history")
    repository.create("camping", "怎样组织一次周末露营？", _members("camping", 4))
    repository.create("enterprise-ai", "企业采购如何评估 AI Agent？", _members("ai", 4))
    client = TestClient(create_app(repository))

    response = client.get(
        "/participants/viewer/table-recommendations?viewer_id=viewer&limit=2"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["personalized"] is True
    assert payload["signal_count"] == 1
    assert payload["signal_types"] == ["table_selected"]
    assert [item["table_id"] for item in payload["items"]] == [
        "enterprise-ai", "camping",
    ]
    first = payload["items"][0]
    assert first["based_on_table_id"] == "history"
    assert first["based_on_question"] == "AI Agent 进入企业为何卡在采购？"
    assert "曾关注" in first["reason"]
    assert "AI Agent 进入企业为何卡在采购" in first["reason"]
    assert "selected-history" not in response.text


def test_repeated_messages_are_capped_and_only_public_topic_role_context_is_returned() -> None:
    repository = InMemoryTableRepository()
    repository.create(
        "practice-history",
        "如何让社区项目真正落地？",
        [_seed("viewer", "运营实践者"), _seed("partner", "研究员")],
    )
    for turn_id in range(1, 6):
        repository.append_turn(
            "practice-history",
            HumanTurn(
                turn_id=turn_id,
                participant_id="viewer",
                text=f"这是不会出现在推荐响应里的私密发言 {turn_id}",
            ),
        )
    repository.close_table("practice-history")
    repository.create(
        "complete-roles",
        "一个全新的讨论主题",
        _members("complete", 4),
    )
    repository.create(
        "needs-practice",
        "另一个全新的讨论主题",
        _members(
            "needs",
            4,
            roles=["产品负责人", "研究员", "桥梁者", "观察者"],
        ),
    )
    response = TestClient(create_app(repository)).get(
        "/participants/viewer/table-recommendations?viewer_id=viewer&limit=2"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_count"] == 3
    assert payload["signal_types"] == ["human_message"]
    assert payload["items"][0]["table_id"] == "needs-practice"
    assert payload["items"][0]["matched_role_gap"] == "实践者"
    assert "运营实践者" in payload["items"][0]["reason"]
    assert "私密发言" not in response.text
    assert "evidence_turns" not in response.text


def test_only_positive_follow_up_states_influence_personalization() -> None:
    repository = InMemoryTableRepository()
    repository.create("history", "如何验证一次产品试点？", [_seed("viewer")])
    repository.close_table("history")
    repository.create("candidate", "产品试点如何进入采购？", _members("candidate", 3))
    history = {state.table_id: state for state in repository.list_tables(include_closed=True)}
    events = [
        BehaviorEvent(
            event_id="blocked",
            participant_id="viewer",
            event_type="follow_up_outcome",
            table_id="history",
            state_version=1,
            detail="status:blocked",
        ),
        BehaviorEvent(
            event_id="dismissed",
            participant_id="viewer",
            event_type="follow_up_outcome",
            table_id="history",
            state_version=1,
            detail="status:dismissed",
        ),
        BehaviorEvent(
            event_id="completed",
            participant_id="viewer",
            event_type="follow_up_outcome",
            table_id="history",
            state_version=1,
            detail="status:completed",
        ),
        BehaviorEvent(
            event_id="someone-else",
            participant_id="other",
            event_type="table_selected",
            table_id="history",
        ),
    ]

    result = build_personalized_table_recommendations(
        "viewer",
        [repository.get("candidate")],
        history,
        events,
    )

    assert result.personalized is True
    assert result.signal_count == 1
    assert result.signal_types == ["follow_up_outcome"]
    assert result.items[0].based_on_table_id == "history"


def test_behavior_reset_immediately_restores_cold_start_after_json_restart(tmp_path) -> None:
    path = tmp_path / "recommendations.json"
    repository = JsonTableRepository(path)
    repository.create("history", "企业 AI 采购", _members("history", 2))
    repository.record_behavior_event(BehaviorEvent(
        event_id="selected",
        participant_id="viewer",
        event_type="table_selected",
        table_id="history",
    ))
    repository.close_table("history")
    repository.create("target", "企业如何采购 AI？", _members("target", 4))
    client = TestClient(create_app(repository))
    before = client.get(
        "/participants/viewer/table-recommendations?viewer_id=viewer"
    )

    cleared = client.delete(
        "/participants/viewer/behavior-events?viewer_id=viewer"
    )
    restarted = TestClient(create_app(JsonTableRepository(path)))
    after = restarted.get(
        "/participants/viewer/table-recommendations?viewer_id=viewer"
    )

    assert before.json()["personalized"] is True
    assert cleared.status_code == 204
    assert after.status_code == 200
    assert after.json()["personalized"] is False
    assert after.json()["signal_count"] == 0
    assert after.json()["items"][0]["table_id"] == "target"
    assert JsonTableRepository(path).get("history").conversation.closed is True


def test_table_recommendations_require_self_identity_and_bound_limit() -> None:
    repository = InMemoryTableRepository()
    repository.create("candidate", "Q", _members("candidate", 3))
    client = TestClient(create_app(repository, identity_resolver=_header_identity))

    assert client.get(
        "/participants/viewer/table-recommendations?viewer_id=viewer"
    ).status_code == 401
    assert client.get(
        "/participants/viewer/table-recommendations?viewer_id=viewer",
        headers={"X-User-ID": "other"},
    ).status_code == 403
    valid = client.get(
        "/participants/viewer/table-recommendations?viewer_id=viewer",
        headers={"X-User-ID": "viewer"},
    )
    assert valid.status_code == 200
    assert client.get(
        "/participants/viewer/table-recommendations?viewer_id=viewer&limit=11",
        headers={"X-User-ID": "viewer"},
    ).status_code == 422
