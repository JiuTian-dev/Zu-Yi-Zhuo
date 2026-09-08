"""Strategist proposal adapter; Coordinator still owns all writes."""

from app.domain import Action, ContentAnalysis, InterventionProposal, ParticipationAnalysis
from app.orchestrator.context import AgentContext
from app.orchestrator.loop import decide_intervention


def propose_action(
    context: AgentContext,
    content: ContentAnalysis | None = None,
    participation: ParticipationAnalysis | None = None,
) -> InterventionProposal:
    gate, route = decide_intervention(context.table_state)
    action = route.action.value if gate.should_speak else Action.SILENCE.value
    evidence = route.evidence_turns if gate.should_speak else []
    target = route.target_participant_id if action == Action.PASS.value else None
    return InterventionProposal(
        input_state_version=context.input_state_version,
        action=action,
        target_participant_id=target,
        rationale="deterministic coordinator proposal",
        evidence_turns=evidence,
        confidence=route.confidence if gate.should_speak else gate.confidence,
    )
