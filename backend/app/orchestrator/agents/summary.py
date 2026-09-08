"""Stage summary specialist adapter and deterministic fallback."""

from app.domain import StageSummaryDraft
from app.orchestrator.agents.base import StructuredSpecialist
from app.orchestrator.checkpoint import build_fallback_summary_draft
from app.orchestrator.context import AgentContext


class StageSummarizerAgent(StructuredSpecialist[StageSummaryDraft]):
    def __init__(self, *, trigger: str = "manual") -> None:
        super().__init__(
            role="stage_summarizer",
            task="Extract a four-block evidence-bound stage checkpoint.",
            schema=StageSummaryDraft,
            fallback_factory=lambda context: build_fallback_summary_draft(
                context.table_state,
                context.delta_turns,
                trigger=trigger,
            ),
        )


def fallback_summary(context: AgentContext, trigger: str) -> StageSummaryDraft:
    return build_fallback_summary_draft(context.table_state, context.delta_turns, trigger=trigger)
