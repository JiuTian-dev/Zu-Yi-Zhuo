"""Evidence-first deterministic action routing; host wording belongs elsewhere."""

from app.domain import Action, DisagreementType, GateDecision, Level, Phase, RouteDecision, TableState

MISMATCHES = {DisagreementType.LAYER_MISMATCH, DisagreementType.DEFINITION_MISMATCH}


def _unique(items) -> list[int]:
    return sorted({turn for item in items for turn in item.evidence_turns})


def _target(state: TableState) -> str | None:
    return next((pid for pid, person in state.participants.items() if person.good_pass_opportunity), None)


def route(state: TableState, gate: GateDecision) -> RouteDecision:
    """Choose one of six actions without generating host text."""
    if not gate.should_speak:
        return RouteDecision()
    if gate.safety_override:
        return RouteDecision(action=Action.REFRAME, evidence_turns=gate.evidence_turns, confidence=.99)

    target = _target(state)
    mismatches = [item for item in state.disagreements if item.disagreement_type in MISMATCHES]
    if mismatches:
        return RouteDecision(action=Action.REFRAME, target_participant_id=target,
                             evidence_turns=_unique(mismatches), confidence=.9)
    conflicts = [item for item in state.disagreements if item.disagreement_type is DisagreementType.FACT_CONFLICT]
    if conflicts:
        return RouteDecision(action=Action.GROUND, evidence_turns=_unique(conflicts), confidence=.9)
    if target:
        return RouteDecision(action=Action.PASS, target_participant_id=target,
                             evidence_turns=gate.evidence_turns, confidence=.85)
    loops = [item for item in state.open_loops if item.priority is Level.HIGH]
    if loops:
        return RouteDecision(action=Action.PROBE, evidence_turns=_unique(loops), confidence=.85)
    if state.close_readiness is Level.HIGH and (state.phase is Phase.CLOSE or state.momentum is Level.LOW):
        return RouteDecision(action=Action.CLOSE, evidence_turns=gate.evidence_turns, confidence=.9)
    return RouteDecision()
