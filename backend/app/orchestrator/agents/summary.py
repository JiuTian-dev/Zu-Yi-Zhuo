"""Stage summary specialist adapter and deterministic fallback."""

from app.domain import StageSummaryDraft, StageSummaryTrigger
from app.orchestrator.agents.base import StructuredSpecialist
from app.orchestrator.checkpoint import build_fallback_summary_draft
from app.orchestrator.context import AgentContext


class StageSummarizerAgent(StructuredSpecialist[StageSummaryDraft]):
    def __init__(self, *, trigger: StageSummaryTrigger = "manual") -> None:
        super().__init__(
            role="stage_summarizer",
            task="Extract a four-block evidence-bound stage checkpoint.",
            schema=StageSummaryDraft,
            fallback_factory=lambda context: build_fallback_summary_draft(
                context.table_state,
                context.delta_turns,
                trigger=trigger,
            ),
            config={"temperature": 0.2, "max_output_tokens": 1600},
            instructions=(
                f"This checkpoint was requested with trigger={trigger}; do not choose a trigger yourself. "
                "Keep the current phase and cover exactly the supplied delta_turns. "
                "All public text combined must be at most 480 characters, preferably 150–300 Chinese characters. "
                "clarified records what a named speaker actually said, not what the group has agreed to. "
                "In public text use display_name only, never internal IDs, guest labels, or technical annotations. "
                "Preserve negation, uncertainty and who holds each view. Never infer agreement from silence. "
                "Do not invent motives, diagnoses, emotions, causality, experiences or facts. "
                "disagreements needs explicitly different views from the cited speakers; different examples alone "
                "are not disagreements. missing may contain only questions or gaps raised in the supplied turns. "
                "next_focus is one short unresolved question already raised by a cited turn, or null. "
                "Use empty lists when there is nothing supported; no headings, slogans, or advice."
            ),
        )


def fallback_summary(context: AgentContext, trigger: str) -> StageSummaryDraft:
    return build_fallback_summary_draft(context.table_state, context.delta_turns, trigger=trigger)
