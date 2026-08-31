"""Small process-local repository used by the first HTTP integration slice."""

from collections.abc import Sequence

from app.domain import HumanTurn, ParticipantSeed, TableState
from app.domain.schemas import ParticipantState
from app.orchestrator import build_initial_state, observe_turn


class InMemoryTableRepository:
    """Store immutable state snapshots and committed human turns by table."""

    def __init__(self) -> None:
        self._states: dict[str, list[TableState]] = {}
        self._turns: dict[str, list[HumanTurn]] = {}

    def create(
        self, table_id: str, core_question: str, participants: Sequence[ParticipantSeed]
    ) -> TableState:
        if table_id in self._states:
            raise ValueError(f"table already exists: {table_id}")
        state = build_initial_state(table_id, core_question, participants)
        self._states[table_id] = [state]
        self._turns[table_id] = []
        return state.model_copy(deep=True)

    def get(self, table_id: str) -> TableState:
        try:
            return self._states[table_id][-1].model_copy(deep=True)
        except KeyError as error:
            raise KeyError(f"unknown table: {table_id}") from error

    def add_participant(self, table_id: str, seed: ParticipantSeed) -> TableState:
        state = self.get(table_id)
        if seed.participant_id in state.participants:
            raise ValueError(f"participant already exists: {seed.participant_id}")
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.participants[seed.participant_id] = ParticipantState(
            participant_id=seed.participant_id,
            display_name=seed.display_name,
            role=seed.role,
            declared_position=seed.declared_position,
            unused_relevant_experience=seed.relevant_experience,
            engagement="low",
        )
        return self._append(table_id, updated)

    def remove_participant(self, table_id: str, participant_id: str) -> TableState:
        """Remove a departing participant while preserving prior snapshots."""
        state = self.get(table_id)
        if participant_id not in state.participants:
            raise ValueError(f"unknown participant: {participant_id}")
        updated = state.model_copy(deep=True)
        updated.version += 1
        del updated.participants[participant_id]
        return self._append(table_id, updated)

    def append_turn(self, table_id: str, turn: HumanTurn) -> TableState:
        """Commit a human turn; the WebSocket adapter will use this helper later."""
        committed = turn.model_copy(deep=True)
        state = observe_turn(self.get(table_id), committed)
        self._turns[table_id].append(committed)
        return self._append(table_id, state)

    def append_intervention_state(self, table_id: str, state: TableState) -> TableState:
        """Commit the one follow-up snapshot produced by a real host intervention."""
        latest = self.get(table_id)
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("intervention state must be the next snapshot for its table")
        return self._append(table_id, state)

    def append_safety_state(self, table_id: str, state: TableState) -> TableState:
        """Commit a safety-only snapshot without recording the intercepted human turn."""
        latest = self.get(table_id)
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("safety state must be the next snapshot for its table")
        return self._append(table_id, state)

    def replay(self, table_id: str, from_version: int | None = None) -> list[TableState]:
        snapshots = sorted(self._states[table_id], key=lambda state: state.version)
        if from_version is not None:
            if not any(state.version == from_version for state in snapshots):
                raise ValueError(f"unknown state version: {from_version}")
            snapshots = [state for state in snapshots if state.version >= from_version]
        return [state.model_copy(deep=True) for state in snapshots]

    def turns(self, table_id: str) -> list[HumanTurn]:
        self.get(table_id)
        return [turn.model_copy(deep=True) for turn in self._turns[table_id]]

    def _append(self, table_id: str, state: TableState) -> TableState:
        snapshot = TableState.model_validate(state.model_dump())
        self._states[table_id].append(snapshot)
        return snapshot.model_copy(deep=True)
