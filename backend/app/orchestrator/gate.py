"""Silence-first deterministic intervention gate."""

from app.domain import DisagreementType, GateDecision, Level, Phase, SafetyLevel, TableState

MISMATCHES = {DisagreementType.LAYER_MISMATCH, DisagreementType.DEFINITION_MISMATCH}


def _turns(state: TableState) -> list[int]:
    participant_evidence = [item for person in state.participants.values()
                            for item in ([person.current_position] if person.current_position else []) + person.key_contributions]
    promising = [state.conversation.most_promising_thread] if state.conversation.most_promising_thread else []
    groups = (state.conversation.risk_flags, state.disagreements, state.open_loops,
              state.new_insights, state.consensus, state.intervention.reasons_to_speak,
              state.intervention.reasons_to_stay_silent, participant_evidence, promising)
    return sorted({turn for group in groups for item in group for turn in item.evidence_turns})


def _has_candidate(state: TableState) -> bool:
    disagreements = state.disagreements
    close = state.close_readiness is Level.HIGH and (state.phase is Phase.CLOSE or state.momentum is Level.LOW)
    return bool(
        any(item.disagreement_type in MISMATCHES | {DisagreementType.FACT_CONFLICT} for item in disagreements)
        or any(person.good_pass_opportunity for person in state.participants.values())
        or any(item.priority is Level.HIGH for item in state.open_loops)
        or close
    )


def evaluate_gate(state: TableState) -> GateDecision:
    """Decide only whether intervention is warranted; default to silence."""
    evidence = _turns(state)
    if state.conversation.safety_level is SafetyLevel.CRITICAL:
        return GateDecision(should_speak=True, safety_override=True, evidence_turns=evidence,
                            reasons_to_speak=["critical safety requires intervention"],
                            reasons_to_stay_silent=[], confidence=.99)
    if state.intervention.last_action.value != "SILENCE" and state.intervention.human_turns_since_last_intervention < 2:
        return GateDecision(reasons_to_stay_silent=["cooldown requires two human turns"], confidence=.99)
    if not _has_candidate(state):
        return GateDecision(reasons_to_stay_silent=["natural progression has no new intervention value"], confidence=.95)
    if not evidence:
        return GateDecision(reasons_to_stay_silent=["candidate lacks turn evidence"], confidence=.7)
    return GateDecision(should_speak=True, evidence_turns=evidence,
                        reasons_to_speak=["high-value intervention candidate exists"],
                        reasons_to_stay_silent=[], confidence=.9)
