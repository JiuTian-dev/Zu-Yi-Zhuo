"""Transport-neutral, evidence-backed cold-start nudge execution."""

from dataclasses import dataclass

from app.domain import AgentActionEvent, GateDecision, InterventionRecord, RouteDecision, TableState
from app.domain.schemas import EvidenceStatement
from app.orchestrator import generate_host_event_with_provider, record_intervention
from app.orchestrator.nudge import build_nudge_decision
from app.providers import LLMProvider

from .intervention import build_intervention_record


class NudgeUnavailable(ValueError):
    """The table cannot produce a nudge with its current evidence/lifecycle."""


class NudgeCooldown(ValueError):
    """The table still requires human space after the previous intervention."""


@dataclass(frozen=True)
class NudgeResult:
    gate: GateDecision
    route: RouteDecision
    action: AgentActionEvent
    state: TableState
    record: InterventionRecord


async def run_nudge(
    repository,
    table_id: str,
    participant_id: str,
    provider: LLMProvider | None = None,
) -> NudgeResult:
    """Build and atomically commit one nudge using the shared Host path."""
    state = repository.get(table_id)
    if participant_id not in state.participants:
        raise PermissionError(f"unknown participant: {participant_id}")
    if state.conversation.closed:
        raise NudgeUnavailable("table is already closed")
    if state.conversation.soft_expired:
        raise NudgeUnavailable("table is soft-expired")
    if state.conversation.safety_level.value == "critical":
        raise NudgeUnavailable("table is paused for safety review")
    turns = repository.turns(table_id)
    if not turns:
        raise NudgeUnavailable("a cold-start nudge requires a committed human turn")
    if (
        state.intervention.last_action.value != "SILENCE"
        and state.intervention.human_turns_since_last_intervention < 2
    ):
        raise NudgeCooldown("two human turns are required between Agent interventions")

    evidence_turn = turns[-1].turn_id
    gate, route = build_nudge_decision(state, evidence_turn)
    action = await generate_host_event_with_provider(state, route, None, provider)
    final_state = record_intervention(state, route, f"{table_id}:agent:{state.version + 1}")
    final_state.intervention.reasons_to_speak = [EvidenceStatement(
        text="首条表达暂未获得自然回应，主动递一句轻问",
        evidence_turns=[evidence_turn],
    )]
    action = action.model_copy(update={"state_version": final_state.version})
    model_name = str(
        getattr(provider, "model", None)
        or (type(provider).__name__ if provider is not None else "deterministic-demo")
    )
    record = build_intervention_record(
        table_id, final_state, route, action, model=model_name
    )
    committed = repository.append_intervention_bundle(table_id, final_state, record)
    return NudgeResult(gate, route, action, committed, record)
