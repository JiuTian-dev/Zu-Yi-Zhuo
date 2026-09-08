"""Content analyst contract adapter."""

from app.domain import ContentAnalysis
from app.orchestrator.agents.base import StructuredSpecialist
from app.orchestrator.context import AgentContext


def fallback_content_analysis(context: AgentContext) -> ContentAnalysis:
    turn_ids = [turn.turn_id for turn in context.delta_turns]
    return ContentAnalysis(
        input_state_version=context.input_state_version,
        clarified_points=[],
        new_insights=[],
        disagreements=[],
        open_questions=[],
        suggested_phase=context.table_state.phase,
        confidence=0.0 if not turn_ids else 0.5,
    )


class ContentAnalystAgent(StructuredSpecialist[ContentAnalysis]):
    def __init__(self) -> None:
        super().__init__(
            role="content_analyst",
            task="Analyze discussion content without choosing a public host action.",
            schema=ContentAnalysis,
            fallback_factory=fallback_content_analysis,
        )
