"""Participation analyst contract adapter."""

from app.domain import ParticipationAnalysis
from app.orchestrator.agents.base import StructuredSpecialist
from app.orchestrator.context import AgentContext


def fallback_participation_analysis(context: AgentContext) -> ParticipationAnalysis:
    counts: dict[str, int] = {}
    for turn in context.delta_turns:
        counts[turn.participant_id] = counts.get(turn.participant_id, 0) + 1
    dominant = [participant_id for participant_id, count in counts.items() if count >= 2]
    underheard = [participant_id for participant_id in context.table_state.participants if counts.get(participant_id, 0) == 0]
    evidence = [turn.turn_id for turn in context.delta_turns]
    return ParticipationAnalysis(
        input_state_version=context.input_state_version,
        dominant_participant_ids=dominant,
        underheard_participant_ids=underheard,
        pass_candidate_id=underheard[0] if underheard else None,
        evidence_turns=evidence if underheard else [],
        confidence=0.5 if evidence else 0.0,
    )


class ParticipationAnalystAgent(StructuredSpecialist[ParticipationAnalysis]):
    def __init__(self) -> None:
        super().__init__(
            role="participation_analyst",
            task="Analyze participation balance without writing table state.",
            schema=ParticipationAnalysis,
            fallback_factory=fallback_participation_analysis,
        )
