"""Evidence verifier for unpublished stage summary drafts."""

from app.domain import StageSummaryDraft, SummaryVerification
from app.orchestrator.context import AgentContext


def verify_summary_draft(draft: StageSummaryDraft, context: AgentContext) -> SummaryVerification:
    committed = {turn.turn_id for turn in context.delta_turns}
    evidence_items = [
        *draft.clarified,
        *draft.disagreements,
        *draft.missing,
        *([draft.next_focus] if draft.next_focus is not None else []),
    ]
    evidence = {turn_id for item in evidence_items for turn_id in item.evidence_turns}
    complete = all(turn_id in committed for turn_id in evidence)
    attribution_safe = all(
        not item.participant_ids or set(item.participant_ids).issubset(context.table_state.participants)
        for item in draft.disagreements
    )
    unsupported = [] if complete else ["summary evidence is outside the current committed context"]
    corrections = [] if attribution_safe else ["summary attribution contains an unknown participant"]
    return SummaryVerification(
        decision="approved" if complete and attribution_safe else "reject",
        evidence_complete=complete,
        attribution_safe=attribution_safe,
        unsupported_claims=unsupported,
        correction_notes=corrections,
    )


class SummaryVerifierAgent:
    """Small deterministic verifier kept behind an agent-shaped interface."""

    def verify(self, draft: StageSummaryDraft, context: AgentContext) -> SummaryVerification:
        return verify_summary_draft(draft, context)
