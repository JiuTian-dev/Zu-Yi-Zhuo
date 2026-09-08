"""Deterministic checkpoint policy and safe summary fallback."""

from dataclasses import dataclass

from app.domain import HumanTurn, StageSummary, StageSummaryDraft, StageSummaryTrigger, TableState


@dataclass(frozen=True)
class CheckpointDecision:
    """Whether semantic checkpoint analysis should run; trigger stays provisional."""

    eligible: bool
    trigger: StageSummaryTrigger | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CheckpointPolicy:
    min_new_turns: int = 4
    min_distinct_participants: int = 2
    cooldown_turns: int = 4
    force_after_turns: int = 12

    def evaluate(
        self,
        turns: tuple[HumanTurn, ...],
        *,
        latest_summary: StageSummary | None = None,
        semantic_trigger: StageSummaryTrigger | None = None,
        pre_close: bool = False,
        manual_requested: bool = False,
    ) -> CheckpointDecision:
        if not turns:
            return CheckpointDecision(False, None, ("no uncovered turns",))
        if manual_requested:
            return CheckpointDecision(True, "manual", ("participant requested checkpoint",))
        if pre_close:
            return CheckpointDecision(True, "pre_close", ("pre-close review",))
        if semantic_trigger is not None:
            return CheckpointDecision(True, semantic_trigger, ("semantic checkpoint candidate",))

        new_turns = len(turns)
        speakers = {turn.participant_id for turn in turns}
        since_checkpoint = (
            turns[-1].turn_id - latest_summary.covered_turn_end if latest_summary is not None else new_turns
        )
        if since_checkpoint < self.cooldown_turns:
            return CheckpointDecision(False, None, ("checkpoint cooldown",))
        if new_turns >= self.force_after_turns:
            return CheckpointDecision(True, None, ("forced eligibility review",))
        if new_turns < self.min_new_turns:
            return CheckpointDecision(False, None, ("insufficient new turns",))
        if len(speakers) < self.min_distinct_participants:
            return CheckpointDecision(False, None, ("insufficient participant coverage",))
        return CheckpointDecision(True, None, ("minimum review sample reached",))


def build_fallback_summary_draft(
    state: TableState,
    turns: tuple[HumanTurn, ...],
    *,
    trigger: StageSummaryTrigger,
) -> StageSummaryDraft:
    """Produce a minimal evidence-safe draft when model output cannot be trusted."""

    if not turns:
        raise ValueError("a checkpoint requires at least one uncovered turn")
    ordered = sorted(turns, key=lambda turn: turn.turn_id)
    if len({turn.turn_id for turn in ordered}) != len(ordered):
        raise ValueError("checkpoint turns must have unique turn_id values")
    last_turn = ordered[-1]
    excerpt = last_turn.text.strip()
    if len(excerpt) > 64:
        excerpt = f"{excerpt[:64].rstrip()}…"
    return StageSummaryDraft(
        input_state_version=state.version,
        phase=state.phase,
        trigger=trigger,
        covered_turn_start=ordered[0].turn_id,
        covered_turn_end=last_turn.turn_id,
        clarified=[],
        disagreements=[],
        missing=[{
            "text": "还需要其他成员回应。",
            "evidence_turns": [last_turn.turn_id],
        }],
        next_focus={
            "text": f"回应这句话：{excerpt}",
            "evidence_turns": [last_turn.turn_id],
        },
    )
