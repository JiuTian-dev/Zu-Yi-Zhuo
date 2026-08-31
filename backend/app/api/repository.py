"""Small repositories used by the first HTTP integration slice."""

from collections.abc import Sequence
import json
import os
from pathlib import Path
import tempfile

from app.domain import GroundingCard, HumanTurn, ParticipantSeed, TableState
from app.domain.schemas import ParticipantState
from app.orchestrator import build_initial_state, observe_turn


class InMemoryTableRepository:
    """Store immutable state snapshots and committed human turns by table."""

    def __init__(self) -> None:
        self._states: dict[str, list[TableState]] = {}
        self._turns: dict[str, list[HumanTurn]] = {}
        self._trusted_grounding_cards: dict[str, GroundingCard] = {}

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

    def set_trusted_grounding_card(self, table_id: str, card: GroundingCard) -> None:
        """Stage one validated demo-injected source for the table's next GROUND action."""
        self.get(table_id)
        if not all(value.strip() for value in (card.title, card.excerpt, card.source_ref)):
            raise ValueError("grounding card title, excerpt, and source_ref must be non-empty")
        self._trusted_grounding_cards[table_id] = card.model_copy(deep=True)

    def take_trusted_grounding_card(self, table_id: str) -> GroundingCard | None:
        """Consume the staged source so it cannot be silently reused for later claims."""
        self.get(table_id)
        card = self._trusted_grounding_cards.pop(table_id, None)
        return card.model_copy(deep=True) if card is not None else None

    def _append(self, table_id: str, state: TableState) -> TableState:
        snapshot = TableState.model_validate(state.model_dump())
        self._states[table_id].append(snapshot)
        return snapshot.model_copy(deep=True)


class JsonTableRepository(InMemoryTableRepository):
    """A small, atomically-written JSON snapshot store for one-process deployments."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            self._states, self._turns, self._trusted_grounding_cards = self._load()

    def create(
        self, table_id: str, core_question: str, participants: Sequence[ParticipantSeed]
    ) -> TableState:
        if table_id in self._states:
            raise ValueError(f"table already exists: {table_id}")
        state = build_initial_state(table_id, core_question, participants)
        states = {**self._states, table_id: [state]}
        turns = {**self._turns, table_id: []}
        self._commit(states, turns, self._trusted_grounding_cards)
        return state.model_copy(deep=True)

    def append_turn(self, table_id: str, turn: HumanTurn) -> TableState:
        committed = turn.model_copy(deep=True)
        state = observe_turn(self.get(table_id), committed)
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        turns = {**self._turns, table_id: [*self._turns[table_id], committed]}
        self._commit(states, turns, self._trusted_grounding_cards)
        return snapshot.model_copy(deep=True)

    def set_trusted_grounding_card(self, table_id: str, card: GroundingCard) -> None:
        """Stage a source and persist it before acknowledging the write."""
        self.get(table_id)
        if not all(value.strip() for value in (card.title, card.excerpt, card.source_ref)):
            raise ValueError("grounding card title, excerpt, and source_ref must be non-empty")
        cards = {**self._trusted_grounding_cards, table_id: card.model_copy(deep=True)}
        self._commit(self._states, self._turns, cards)

    def take_trusted_grounding_card(self, table_id: str) -> GroundingCard | None:
        """Consume a source only after the removal is atomically persisted."""
        self.get(table_id)
        card = self._trusted_grounding_cards.get(table_id)
        if card is None:
            return None
        cards = dict(self._trusted_grounding_cards)
        cards.pop(table_id)
        self._commit(self._states, self._turns, cards)
        return card.model_copy(deep=True)

    def _append(self, table_id: str, state: TableState) -> TableState:
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        self._commit(states, self._turns, self._trusted_grounding_cards)
        return snapshot.model_copy(deep=True)

    def _commit(
        self,
        states: dict[str, list[TableState]],
        turns: dict[str, list[HumanTurn]],
        trusted_grounding_cards: dict[str, GroundingCard] | None = None,
    ) -> None:
        cards = trusted_grounding_cards if trusted_grounding_cards is not None else self._trusted_grounding_cards
        payload = {
            "tables": {
                table_id: {
                    "states": [state.model_dump(mode="json") for state in snapshots],
                    "turns": [turn.model_dump(mode="json") for turn in turns[table_id]],
                }
                for table_id, snapshots in states.items()
            },
            "trusted_grounding_cards": {
                table_id: card.model_dump(mode="json") for table_id, card in cards.items()
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, prefix=f".{self.path.name}.",
                suffix=".tmp", delete=False,
            ) as handle:
                temp_name = handle.name
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            Path(temp_name).replace(self.path)
        finally:
            if temp_name is not None:
                Path(temp_name).unlink(missing_ok=True)
        self._states, self._turns = states, turns
        self._trusted_grounding_cards = {
            table_id: card.model_copy(deep=True) for table_id, card in cards.items()
        }

    def _load(self) -> tuple[
        dict[str, list[TableState]], dict[str, list[HumanTurn]], dict[str, GroundingCard]
    ]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid persistence file: {self.path}") from error
        if (not isinstance(payload, dict) or set(payload) not in ({"tables"}, {"tables", "trusted_grounding_cards"})
                or not isinstance(payload["tables"], dict)):
            raise ValueError("invalid persistence file: expected {'tables': {...}}")
        states: dict[str, list[TableState]] = {}
        turns: dict[str, list[HumanTurn]] = {}
        for table_id, table in payload["tables"].items():
            if not isinstance(table_id, str) or not table_id or not isinstance(table, dict) or set(table) != {"states", "turns"}:
                raise ValueError(f"invalid persistence file: malformed table {table_id!r}")
            try:
                snapshots = [TableState.model_validate(item) for item in table["states"]]
                messages = [HumanTurn.model_validate(item) for item in table["turns"]]
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid persistence file: invalid data for table {table_id!r}") from error
            if not snapshots or any(state.table_id != table_id for state in snapshots):
                raise ValueError(f"invalid persistence file: incompatible states for table {table_id!r}")
            if [state.version for state in snapshots] != list(range(len(snapshots))):
                raise ValueError(f"invalid persistence file: incompatible versions for table {table_id!r}")
            if [turn.turn_id for turn in messages] != sorted({turn.turn_id for turn in messages}):
                raise ValueError(f"invalid persistence file: incompatible turns for table {table_id!r}")
            states[table_id] = snapshots
            turns[table_id] = messages
        raw_cards = payload.get("trusted_grounding_cards", {})
        if not isinstance(raw_cards, dict):
            raise ValueError("invalid persistence file: malformed trusted_grounding_cards")
        cards: dict[str, GroundingCard] = {}
        for table_id, raw_card in raw_cards.items():
            if table_id not in states:
                raise ValueError(f"invalid persistence file: grounding card for unknown table {table_id!r}")
            try:
                cards[table_id] = GroundingCard.model_validate(raw_card)
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid persistence file: invalid grounding card for table {table_id!r}") from error
        return states, turns, cards
