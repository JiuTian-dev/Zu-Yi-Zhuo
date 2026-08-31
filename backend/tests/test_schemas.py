import pytest
from pydantic import ValidationError

from app.domain import Action, AgentActionEvent, PersonalCard, SafetyLevel, TableState
from app.domain.schemas import ConversationState, InterventionRecord, InterventionState, ParticipantState, SharedBaseline

def evidence(text: str, turn: int = 1) -> dict:
    return {"text": text, "evidence_turns": [turn]}

def valid_state() -> dict:
    return {
        "table_id": "table-1", "version": 2, "core_question": "AI Agent 进企业卡在哪？",
        "current_subquestion": "采购如何评估风险？", "phase": "explore",
        "momentum": "high", "close_readiness": "low",
        "new_insights": [evidence("试点范围影响采购", 2)], "consensus": [],
        "disagreements": [{**evidence("安全审核是否是首要瓶颈"), "evidence_turns": [1, 3],
                           "disagreement_type": "causal_disagreement", "participant_ids": ["p1", "p2"]}],
        "open_loops": [],
        "participants": {"p1": {
            "participant_id": "p1", "display_name": "林青", "role": "采购负责人", "engagement": "high",
            "last_spoke_turn": 3, "unused_relevant_experience": [{"text": "做过供应商试点", "source_ref": "seed:p1:1"}],
        }},
        "conversation": {"state": "active", "safety_level": "normal"},
        "intervention": {"recommended_action": "PASS", "confidence": 0.8, "human_turns_since_last_intervention": 2},
    }

def test_table_state_serializes_with_string_enums() -> None:
    payload = TableState.model_validate(valid_state()).model_dump(mode="json")
    assert (payload["phase"], payload["disagreements"][0]["disagreement_type"]) == ("explore", "causal_disagreement")

@pytest.mark.parametrize(("field", "limit"), [("new_insights", 8), ("consensus", 5), ("open_loops", 3)])
def test_table_state_rejects_lists_over_limit(field: str, limit: int) -> None:
    data = valid_state()
    items = ([{"question": str(i), "priority": "medium", "evidence_turns": [i + 1]} for i in range(limit + 1)]
             if field == "open_loops" else [evidence(str(i), i + 1) for i in range(limit + 1)])
    data[field] = items[:limit]
    assert len(getattr(TableState.model_validate(data), field)) == limit
    data[field] = items
    with pytest.raises(ValidationError): TableState.model_validate(data)

@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_action_event_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        AgentActionEvent(action="PASS", target_participant_id="p1", visual_hint={"pose": "pass"},
                         evidence_turns=[3], state_version=2, confidence=confidence)

def test_action_enum_matches_frontend_contract() -> None:
    assert {item.value for item in Action} == {"SILENCE", "PASS", "PROBE", "REFRAME", "GROUND", "CLOSE"}

def test_suggestion_cannot_be_encoded_as_commitment() -> None:
    base = {"table_id": "table-1", "participant_id": "p1", "state_version": 2}
    suggestion = {"item_type": "suggestion", "text": "可以先试点", "is_commitment": True, "evidence_turns": [3]}
    ownerless = {"item_type": "commitment", "text": "下周开试点", "is_commitment": True, "evidence_turns": [3]}
    for invalid in (suggestion, ownerless):
        with pytest.raises(ValidationError): PersonalCard(**base, suggested_next_actions=[invalid])
    owned = {**ownerless, "owner_participant_id": "p1"}
    assert PersonalCard(**base, suggested_next_actions=[owned]).suggested_next_actions[0].is_commitment

def test_relationship_suggestion_uses_participant_and_reason() -> None:
    card = PersonalCard(table_id="table-1", participant_id="p1", state_version=2,
                        worth_continuing_with=[{"participant_id": "p2", "reason": "可继续交叉验证", "evidence_turns": [2]}])
    assert card.worth_continuing_with[0].participant_id == "p2"

def test_visual_hint_serializes_as_structured_json() -> None:
    event = AgentActionEvent(action="REFRAME", text="换个角度看。", visual_hint={"focus": ["p1", "p2"]},
                             evidence_turns=[1, 2], state_version=3, confidence=0.7)
    assert event.model_dump(mode="json")["visual_hint"] == {"focus": ["p1", "p2"]}

@pytest.mark.parametrize("payload", [
    {"action": "PASS", "evidence_turns": [1]}, {"action": "PROBE", "evidence_turns": []},
    {"action": "SILENCE", "evidence_turns": [0]}, {"action": "SILENCE", "evidence_turns": [], "text": "x" * 121},
])
def test_action_context_is_validated(payload: dict) -> None:
    with pytest.raises(ValidationError): AgentActionEvent(**payload, visual_hint={}, state_version=3, confidence=0.7)

def test_participant_map_key_must_match_id() -> None:
    data = valid_state(); data["participants"] = {"wrong": data["participants"]["p1"]}
    with pytest.raises(ValidationError): TableState.model_validate(data)

def test_spec_sections_expose_required_fields() -> None:
    expected = [
        (ParticipantState, "role current_position key_contributions unused_relevant_experience engagement last_spoke_turn good_pass_opportunity"),
        (ConversationState, "state most_promising_thread risk_flags safety_level"),
        (InterventionState, "reasons_to_speak reasons_to_stay_silent recommended_action confidence last_action last_agent_turn_id human_turns_since_last_intervention"),
        (InterventionRecord, "table_id latency_ms model token_usage outcome reflection"),
        (SharedBaseline, "core_question_before key_consensus unresolved_disagreements evolved_question collective_next_steps"),
        (PersonalCard, "what_changed your_contribution worth_continuing_with suggested_next_actions"),
    ]
    assert all(set(fields.split()) <= set(model.model_fields) for model, fields in expected)

def test_safety_and_open_loop_have_independent_semantics() -> None:
    data = valid_state(); data["open_loops"] = [{"question": "谁承担试点风险？", "priority": "high", "evidence_turns": [3]}]
    state = TableState.model_validate(data)
    assert state.conversation.safety_level is SafetyLevel.NORMAL and state.open_loops[0].priority.value == "high"
    data["conversation"]["safety_level"] = "high"
    with pytest.raises(ValidationError): TableState.model_validate(data)
