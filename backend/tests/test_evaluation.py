from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.repository import InMemoryTableRepository
from app.domain import Action, FollowUpOutcome, HumanTurn, InterventionRecord, ParticipantSeed, PeripheralComment
from app.domain.schemas import EvidenceStatement, TokenUsage


def _seed(participant_id: str) -> ParticipantSeed:
    return ParticipantSeed(
        participant_id=participant_id,
        display_name=participant_id,
        role="实践者",
        declared_position="公开立场",
    )


def test_open_evaluation_is_member_scoped_and_has_no_close_private_data() -> None:
    repository = InMemoryTableRepository()
    repository.create("evaluation-open", "如何把讨论变成行动？", [_seed("p1"), _seed("p2")])
    client = TestClient(create_app(repository))

    response = client.get("/tables/evaluation-open/evaluation?participant_id=p1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["table_id"] == "evaluation-open"
    assert payload["closed"] is False
    assert payload["participant_count"] == 2
    assert payload["human_turn_count"] == 0
    assert payload["intervention_count"] == 0
    assert payload["intervention_rate"] == 0.0
    assert payload["effective_intervention_rate"] is None
    assert payload["intervention_phase_counts"] == {
        "opening": 0, "explore": 0, "tension": 0, "deepen": 0, "close": 0,
    }
    assert payload["follow_up_count"] == 0
    assert payload["follow_up_completion_rate"] is None
    assert payload["feedback_completion_rate"] == 0.0
    assert payload["feedback_summary"] is None
    assert "participant_id" not in payload
    assert client.get("/tables/evaluation-open/evaluation?participant_id=ghost").status_code == 403


def test_closed_evaluation_aggregates_feedback_and_follow_up_outcomes() -> None:
    repository = InMemoryTableRepository()
    repository.create("evaluation-closed", "如何把讨论变成行动？", [_seed("p1"), _seed("p2")])
    repository.append_turn(
        "evaluation-closed",
        HumanTurn(turn_id=1, participant_id="p1", text="我会在下周整理验证清单。"),
    )
    closed = repository.close_table("evaluation-closed")
    repository.record_follow_up_outcome(FollowUpOutcome(
        table_id="evaluation-closed",
        follow_up_index=0,
        participant_id="p1",
        status="completed",
    ))
    client = TestClient(create_app(repository))
    feedback = {
        "cognitive_value": 5,
        "relationship_value": 4,
        "action_value": 3,
        "emotional_value": 4,
        "would_join_again": True,
    }
    client.post("/tables/evaluation-closed/feedback?participant_id=p1", json=feedback)
    client.post(
        "/tables/evaluation-closed/feedback?participant_id=p2",
        json={**feedback, "would_join_again": False},
    )

    response = client.get("/tables/evaluation-closed/evaluation?participant_id=p2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state_version"] == closed.version
    assert payload["closed"] is True
    assert payload["human_turn_count"] == 1
    assert payload["follow_up_count"] == 1
    assert payload["follow_up_reported_count"] == 1
    assert payload["follow_up_completed_count"] == 1
    assert payload["follow_up_completion_rate"] == 1.0
    assert payload["feedback_completion_rate"] == 1.0
    assert payload["would_join_again_rate"] == 0.5
    assert payload["feedback_summary"] == {
        "table_id": "evaluation-closed",
        "state_version": closed.version,
        "eligible_participant_count": 2,
        "response_count": 2,
        "cognitive_average": 5.0,
        "relationship_average": 4.0,
        "action_average": 3.0,
        "emotional_average": 4.0,
        "would_join_again_count": 1,
    }
    assert "note" not in response.text and "participant_id" not in response.text


def test_evaluation_derives_intervention_rates_and_snapshot_phase_counts() -> None:
    repository = InMemoryTableRepository()
    repository.create("evaluation-rhythm", "如何把讨论变成行动？", [_seed("p1"), _seed("p2")])
    first = repository.append_turn(
        "evaluation-rhythm", HumanTurn(turn_id=1, participant_id="p1", text="技术试点需要验证。")
    )
    repository.append_intervention_record("evaluation-rhythm", InterventionRecord(
        action=Action.PROBE, text="能补充一个验证案例吗？", visual_hint={"kind": "probe"},
        evidence_turns=[1], state_version=first.version, confidence=.8,
        intervention_id="evaluation-rhythm:1", table_id="evaluation-rhythm", latency_ms=1,
        model="test", token_usage=TokenUsage(input_tokens=0, output_tokens=0),
        reflection=EvidenceStatement(text="无效", evidence_turns=[1]), reflection_effective=False,
    ))
    second = repository.append_turn(
        "evaluation-rhythm", HumanTurn(turn_id=2, participant_id="p2", text="采购责任也需要验证。")
    )
    repository.append_intervention_record("evaluation-rhythm", InterventionRecord(
        action=Action.REFRAME, text="先区分技术与采购责任。", visual_hint={"kind": "reframe"},
        evidence_turns=[1, 2], state_version=second.version, confidence=.8,
        intervention_id="evaluation-rhythm:2", table_id="evaluation-rhythm", latency_ms=1,
        model="test", token_usage=TokenUsage(input_tokens=0, output_tokens=0),
        reflection=EvidenceStatement(text="有效", evidence_turns=[2]), reflection_effective=True,
    ))
    client = TestClient(create_app(repository))

    response = client.get("/tables/evaluation-rhythm/evaluation?participant_id=p1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intervention_rate"] == 1.0
    assert payload["effective_intervention_rate"] == 0.5
    assert payload["intervention_phase_counts"] == {
        "opening": 0, "explore": 1, "tension": 1, "deepen": 0, "close": 0,
    }
    assert sum(payload["intervention_phase_counts"].values()) == payload["intervention_count"] == 2


def test_evaluation_includes_invitation_funnel_and_peripheral_attention_counts() -> None:
    repository = InMemoryTableRepository()
    repository.create("evaluation-funnel", "如何把讨论变成行动？", [_seed("p1"), _seed("p2")])
    candidate_one = _seed("p3")
    candidate_two = _seed("p4")
    first = repository.create_invitation("evaluation-funnel", "p1", candidate_one, "补充实践视角")
    second = repository.create_invitation("evaluation-funnel", "p1", candidate_two, "补充行业视角")
    repository.respond_invitation("evaluation-funnel", first.invitation_id, "p3", True)
    repository.respond_invitation("evaluation-funnel", second.invitation_id, "p4", False)
    state = repository.get("evaluation-funnel")
    repository.append_comment_once(PeripheralComment(
        comment_id="comment-1",
        table_id="evaluation-funnel",
        author_id="observer",
        display_name="旁听者",
        text="我也想知道如何验证这个行动。",
        state_version=state.version,
    ))
    repository.promote_comment_once("evaluation-funnel", "comment-1", "p1")
    repository.close_table("evaluation-funnel")
    client = TestClient(create_app(repository))

    response = client.get("/tables/evaluation-funnel/evaluation?participant_id=p1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["invitation_count"] == 2
    assert payload["invitation_pending_count"] == 0
    assert payload["invitation_accepted_count"] == 1
    assert payload["invitation_declined_count"] == 1
    assert payload["invitation_acceptance_rate"] == 0.5
    assert payload["peripheral_comment_count"] == 1
    assert payload["promoted_comment_count"] == 1
    assert "observer" not in response.text
