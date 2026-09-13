"""Bounded, typed context shared with table specialist agents."""

from dataclasses import dataclass

from app.domain import HumanTurn, StageSummary, TableState


@dataclass(frozen=True)
class AgentContext:
    """One immutable view of the table at a specific state version."""

    table_state: TableState
    delta_turns: tuple[HumanTurn, ...]
    latest_summary: StageSummary | None = None

    @property
    def input_state_version(self) -> int:
        return self.table_state.version


def build_agent_context(
    state: TableState,
    turns: list[HumanTurn],
    *,
    latest_summary: StageSummary | None = None,
    max_delta_turns: int = 24,
) -> AgentContext:
    """Build the model context from a checkpoint plus only the uncovered turn delta."""

    if max_delta_turns < 1:
        raise ValueError("max_delta_turns must be positive")
    if latest_summary is None and state.latest_stage_summary_id is not None:
        raise ValueError("latest published summary must be loaded into AgentContext")
    if latest_summary is not None and (
        latest_summary.summary_id != state.latest_stage_summary_id
        or latest_summary.revision != state.latest_stage_summary_revision
        or latest_summary.status != "published"
        or latest_summary.table_id != state.table_id
        or latest_summary.published_state_version > state.version
    ):
        raise ValueError("latest_summary must match the published TableState summary reference")

    ordered = sorted(turns, key=lambda turn: turn.turn_id)
    if len({turn.turn_id for turn in ordered}) != len(ordered):
        raise ValueError("turn_id values must be unique within AgentContext")
    covered_through = latest_summary.covered_turn_end if latest_summary is not None else 0
    eligible = [turn for turn in ordered if turn.turn_id > covered_through]
    bounded = tuple(turn.model_copy(deep=True) for turn in eligible[-max_delta_turns:])
    summary_copy = latest_summary.model_copy(deep=True) if latest_summary is not None else None
    return AgentContext(table_state=state.model_copy(deep=True), delta_turns=bounded, latest_summary=summary_copy)
