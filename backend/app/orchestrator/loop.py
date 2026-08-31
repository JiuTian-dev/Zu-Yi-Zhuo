"""Small integration seam for one intervention decision cycle."""

from app.domain import Action, GateDecision, RouteDecision, TableState

from .gate import evaluate_gate
from .router import route


def decide_intervention(state: TableState) -> tuple[GateDecision, RouteDecision]:
    """Evaluate the silence-first gate, then route the resulting decision."""
    gate = evaluate_gate(state)
    return gate, route(state, gate)


def record_intervention(previous: TableState, decision: RouteDecision, agent_turn_id: str) -> TableState:
    """Atomically return a new snapshot after a real non-silence intervention."""
    if decision.action is Action.SILENCE:
        raise ValueError("cannot record a SILENCE route as an intervention")
    if not agent_turn_id.strip():
        raise ValueError("agent_turn_id must not be empty")
    if decision.target_participant_id is not None and decision.target_participant_id not in previous.participants:
        raise ValueError("unknown target participant")

    state = previous.model_copy(deep=True)
    state.version += 1
    state.intervention.recommended_action = Action.SILENCE
    state.intervention.last_action = decision.action
    state.intervention.last_agent_turn_id = agent_turn_id
    state.intervention.human_turns_since_last_intervention = 0
    if decision.target_participant_id:
        state.participants[decision.target_participant_id].good_pass_opportunity = False
    return TableState.model_validate(state.model_dump())
