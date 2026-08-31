import pytest
from app.demo import SCENARIOS, flagship_participants
from app.domain import Action, HumanTurn, Level, RouteDecision
from app.domain.schemas import EvidenceStatement, ParticipantState
from app.orchestrator import (build_initial_state, build_personal_card, build_shared_baseline, compute_close_readiness, evaluate_reflection, extract_follow_ups, observe_turn, record_intervention, refresh_close_readiness)
def flagship():
    state = build_initial_state("close", "AI Agent 进入企业卡在哪？", flagship_participants); [state := observe_turn(state, turn) for turn in SCENARIOS["flagship"]]; return state
def after_intervention():
    before = flagship()
    route = RouteDecision(action=Action.REFRAME, target_participant_id="buyer", evidence_turns=[1, 2])
    after = record_intervention(before, route, "int-041"); after = observe_turn(after, HumanTurn(turn_id=4, participant_id="buyer", text="我会补充采购案例。")); after = observe_turn(after, HumanTurn(turn_id=5, participant_id="founder", text="建议先验证小范围试点。"))
    return before, after, route
def test_reflection_marks_zero_turn_as_not_effective():
    state = build_initial_state("empty", "Q", flagship_participants)
    result = evaluate_reflection(state, state, RouteDecision(action=Action.REFRAME, evidence_turns=[1]))
    assert not result.effective and result.score == 0 and result.human_turns_observed == 0 and "不足" in result.strategy_note
def test_reflection_does_not_claim_effect_after_one_turn():
    before = flagship(); _, after, route = after_intervention()
    after.intervention.human_turns_since_last_intervention = 1
    result = evaluate_reflection(before, after, route)
    assert not result.effective and not result.effects and result.score == 0
def test_reflection_target_join_is_a_positive_effect():
    before, after, route = after_intervention()
    result = evaluate_reflection(before, after, route)
    assert any("加入" in effect.text for effect in result.effects)
    person = ParticipantState(participant_id="new", display_name="新成员", role="客户", engagement=Level.HIGH, current_position=EvidenceStatement(text="补充客户案例", evidence_turns=[5]))
    after.participants["new"] = person
    route = route.model_copy(update={"target_participant_id": "new"})
    result = evaluate_reflection(before, after, route)
    assert any("加入" in effect.text for effect in result.effects)
def test_reflection_subquestion_change_is_positive():
    before, after, route = after_intervention()
    after.current_subquestion = "谁承担试点风险？"
    after.open_loops[0].question = after.current_subquestion; after.open_loops[0].evidence_turns = [4]
    result = evaluate_reflection(before, after, route, human_turn_ids=[4, 5])
    assert any("新" in effect.text for effect in result.effects)
def test_reflection_no_change_has_negative_effect():
    before = flagship()
    after = before.model_copy(deep=True)
    after.intervention.human_turns_since_last_intervention = 2
    result = evaluate_reflection(before, after, RouteDecision(action=Action.PROBE, evidence_turns=[1]), human_turn_ids=[1])
    assert not result.effective and not result.effects and not result.negative_effects and "evidence" in result.strategy_note
def test_reflection_score_and_confidence_are_bounded_and_serializable():
    before, after, route = after_intervention(); result = evaluate_reflection(before, after, route)
    payload = result.model_dump(mode="json")
    assert 0 <= result.score <= 1 and 0 <= result.confidence <= 1 and payload["intervention_id"] == "int-041" and isinstance(payload["effects"], list)
@pytest.mark.parametrize(("momentum", "substance", "unresolved", "expected"), [(Level.HIGH, 0, 1, Level.LOW), (Level.MEDIUM, 2, 1, Level.MEDIUM), (Level.LOW, 1, 0, Level.HIGH)])
def test_close_readiness_uses_marginal_value_signals(momentum, substance, unresolved, expected):
    state = flagship().model_copy(deep=True); state.momentum = momentum; state.new_insights = [EvidenceStatement(text=str(i), evidence_turns=[i + 1]) for i in range(substance)]; state.consensus = []; state.open_loops = state.open_loops[:unresolved]; state.disagreements = state.disagreements[:max(0, unresolved - len(state.open_loops))]
    assert compute_close_readiness(state) is expected
    refreshed = refresh_close_readiness(state)
    assert refreshed is not state and state.close_readiness is not refreshed.close_readiness or refreshed.close_readiness is expected
def test_shared_baseline_preserves_q0_q1_and_unresolved_work():
    state = flagship()
    baseline = build_shared_baseline(state, "Q0 原问题", turns=[HumanTurn(turn_id=8, participant_id="buyer", text="我会补充验证清单。")])
    assert baseline.core_question_before == "Q0 原问题" and baseline.evolved_question.text == state.current_subquestion
    assert baseline.unresolved_disagreements == state.disagreements and any(item.is_commitment for item in baseline.collective_next_steps)
    assert all(not item.is_commitment for item in baseline.collective_next_steps[:1])

@pytest.mark.parametrize("participant_id", ["architect", "product", "buyer", "founder"])
def test_personal_card_is_scoped_to_each_real_participant(participant_id):
    card = build_personal_card(flagship(), participant_id)
    assert card.participant_id == participant_id and card.table_id == "close"
    assert all(not item.is_commitment for item in card.suggested_next_actions)
def test_personal_card_rejects_unknown_participant():
    with pytest.raises(ValueError, match="unknown participant"):
        build_personal_card(flagship(), "ghost")
def test_follow_ups_distinguish_explicit_commitment_from_suggestion():
    items = extract_follow_ups([
        HumanTurn(turn_id=10, participant_id="p1", text="建议先做一次小范围试点。"),
        HumanTurn(turn_id=11, participant_id="p2", text="我会在下周整理验证清单。"),
    ])
    assert [item.item_type for item in items] == ["suggestion", "commitment"]
    assert items[0].owner_participant_id is None
    assert items[1].owner_participant_id == "p2"
def test_follow_ups_do_not_auto_commit_plain_action_language():
    items = extract_follow_ups([HumanTurn(turn_id=12, participant_id="p1", text="下周做一个试点。")])
    assert items == []
def test_follow_up_commitment_owner_is_a_real_turn_participant():
    item = extract_follow_ups([HumanTurn(turn_id=13, participant_id="real", text="我负责联系客户。")])[0]
    assert item.is_commitment and item.owner_participant_id == "real"
def test_close_artifacts_keep_suggestions_non_commitments():
    state = flagship(); baseline = build_shared_baseline(state)
    assert all(item.item_type == "suggestion" and item.is_commitment is False
               for item in baseline.collective_next_steps)
