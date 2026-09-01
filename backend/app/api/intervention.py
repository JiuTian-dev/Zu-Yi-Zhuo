"""Shared construction helpers for explainable Host intervention records."""

from app.domain import AgentActionEvent, GroundingCard, InterventionRecord, RouteDecision, TableState
from app.domain.schemas import EvidenceStatement
from app.domain.schemas import TokenUsage


def build_intervention_record(
    table_id: str,
    state: TableState,
    route: RouteDecision,
    action: AgentActionEvent,
    model: str = "deterministic-demo",
    grounding_card: GroundingCard | None = None,
) -> InterventionRecord:
    """Create an audit entry from a committed, validated Host event."""
    evidence = list(action.evidence_turns or route.evidence_turns)
    reasons = list(state.intervention.reasons_to_speak)
    if not reasons:
        reasons = [EvidenceStatement(text="主持动作有现场证据支持", evidence_turns=evidence)]
    return InterventionRecord(
        **action.model_dump(),
        intervention_id=f"{table_id}:intervention:{state.version}",
        table_id=table_id,
        reasons_to_speak=reasons,
        reasons_to_stay_silent=list(state.intervention.reasons_to_stay_silent),
        latency_ms=0,
        model=model,
        token_usage=TokenUsage(input_tokens=0, output_tokens=0),
        grounding_card=grounding_card,
    )
