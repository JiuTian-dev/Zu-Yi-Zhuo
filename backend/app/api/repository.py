"""Small repositories used by the first HTTP integration slice."""

from collections.abc import Callable, Sequence
from functools import wraps
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any

from app.domain import Action, ConversationMode, GroundingCard, HumanTurn, Invitation, InvitationStatus, InterventionRecord, Level, ParticipantSeed, Phase, SafetyLevel, TableState
from app.domain.schemas import ParticipantState
from app.orchestrator import build_initial_state, observe_turn


def _synchronized(method: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize one repository operation while allowing nested calls."""

    @wraps(method)
    def wrapped(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapped


class InMemoryTableRepository:
    """Store immutable state snapshots and committed human turns by table."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._states: dict[str, list[TableState]] = {}
        self._turns: dict[str, list[HumanTurn]] = {}
        self._interventions: dict[str, list[InterventionRecord]] = {}
        self._trusted_grounding_cards: dict[str, GroundingCard] = {}
        self._invitations: dict[str, list[Invitation]] = {}

    @_synchronized
    def create(
        self, table_id: str, core_question: str, participants: Sequence[ParticipantSeed]
    ) -> TableState:
        if table_id in self._states:
            raise ValueError(f"table already exists: {table_id}")
        state = build_initial_state(table_id, core_question, participants)
        self._states[table_id] = [state]
        self._turns[table_id] = []
        self._interventions[table_id] = []
        self._invitations[table_id] = []
        return state.model_copy(deep=True)

    @_synchronized
    def get(self, table_id: str) -> TableState:
        try:
            return self._states[table_id][-1].model_copy(deep=True)
        except KeyError as error:
            raise KeyError(f"unknown table: {table_id}") from error

    @_synchronized
    def list_tables(self, include_closed: bool = False) -> list[TableState]:
        """Return isolated latest snapshots for the public table directory."""
        states = [snapshots[-1] for snapshots in self._states.values() if snapshots]
        if not include_closed:
            states = [state for state in states if not state.conversation.closed]
        return [state.model_copy(deep=True) for state in states]

    @_synchronized
    def add_participant(self, table_id: str, seed: ParticipantSeed) -> TableState:
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
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

    @_synchronized
    def create_invitation(
        self, table_id: str, inviter_id: str, candidate: ParticipantSeed, reason: str
    ) -> Invitation:
        """Create one candidate-scoped invitation without adding a seat yet."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if inviter_id not in state.participants:
            raise ValueError("inviter must be a table participant")
        if candidate.participant_id in state.participants:
            raise ValueError("candidate is already a table participant")
        if any(
            item.candidate.participant_id == candidate.participant_id
            for item in self._invitations[table_id]
        ):
            raise ValueError("candidate already has an invitation for this table")
        invitation = Invitation(
            invitation_id=f"{table_id}:invite:{len(self._invitations[table_id]) + 1}",
            table_id=table_id,
            inviter_id=inviter_id,
            candidate=candidate,
            reason=reason,
        )
        self._invitations[table_id].append(invitation)
        return invitation.model_copy(deep=True)

    @_synchronized
    def invitations(self, table_id: str) -> list[Invitation]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._invitations[table_id]]

    @_synchronized
    def respond_invitation(
        self, table_id: str, invitation_id: str, participant_id: str, accept: bool
    ) -> tuple[Invitation, TableState | None]:
        """Accept/decline an invitation; acceptance atomically adds the seat."""
        state = self.get(table_id)
        invitation = next(
            (item for item in self._invitations[table_id] if item.invitation_id == invitation_id),
            None,
        )
        if invitation is None:
            raise ValueError(f"unknown invitation: {invitation_id}")
        if invitation.candidate.participant_id != participant_id:
            raise PermissionError("only the invited participant may respond")
        requested = InvitationStatus.ACCEPTED if accept else InvitationStatus.DECLINED
        if invitation.status is not InvitationStatus.PENDING:
            if invitation.status is requested:
                return invitation.model_copy(deep=True), state if accept else None
            raise ValueError("invitation has already been resolved")
        if state.conversation.closed:
            raise ValueError("table is closed")
        updated_invitation = invitation.model_copy(update={"status": requested})
        index = self._invitations[table_id].index(invitation)
        if not accept:
            self._invitations[table_id][index] = updated_invitation
            return updated_invitation.model_copy(deep=True), None
        if participant_id in state.participants:
            raise ValueError("candidate is already a table participant")
        updated_state = state.model_copy(deep=True)
        updated_state.version += 1
        seed = invitation.candidate
        updated_state.participants[participant_id] = ParticipantState(
            participant_id=participant_id,
            display_name=seed.display_name,
            role=seed.role,
            declared_position=seed.declared_position,
            unused_relevant_experience=seed.relevant_experience,
            engagement="low",
        )
        self._invitations[table_id][index] = updated_invitation
        committed = self._append(table_id, updated_state)
        return updated_invitation.model_copy(deep=True), committed

    @_synchronized
    def remove_participant(self, table_id: str, participant_id: str) -> TableState:
        """Remove a departing participant while preserving prior snapshots."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if participant_id not in state.participants:
            raise ValueError(f"unknown participant: {participant_id}")
        updated = state.model_copy(deep=True)
        updated.version += 1
        del updated.participants[participant_id]
        return self._append(table_id, updated)

    @_synchronized
    def set_profile_consent(self, table_id: str, participant_id: str, shared: bool) -> TableState:
        """Set one participant's explicit profile-sharing consent."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        participant = state.participants.get(participant_id)
        if participant is None:
            raise ValueError(f"unknown participant: {participant_id}")
        if participant.profile_shared is shared:
            return state
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.participants[participant_id].profile_shared = shared
        return self._append(table_id, updated)

    @_synchronized
    def upgrade_to_sync(self, table_id: str) -> TableState:
        """Atomically switch an eligible table from async to sync mode."""
        state = self.get(table_id)
        if state.conversation.mode is ConversationMode.SYNC:
            return state
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.safety_level is SafetyLevel.CRITICAL:
            raise ValueError("table is paused for safety review")
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.conversation.mode = ConversationMode.SYNC
        updated.conversation.state = "sync_active"
        return self._append(table_id, updated)

    @_synchronized
    def append_turn(self, table_id: str, turn: HumanTurn) -> TableState:
        """Commit a human turn; the WebSocket adapter will use this helper later."""
        if self.get(table_id).conversation.closed:
            raise ValueError("table is closed")
        committed = turn.model_copy(deep=True)
        state = observe_turn(self.get(table_id), committed)
        self._turns[table_id].append(committed)
        return self._append(table_id, state)

    @_synchronized
    def append_message_once(
        self, table_id: str, participant_id: str, text: str, message_id: str
    ) -> tuple[TableState, bool]:
        """Atomically commit one client message, returning ``(state, created)``.

        WebSocket clients may retry after a lost acknowledgement.  The message id
        is scoped to a table: an exact retry is acknowledged as already committed,
        while reusing an id for different content is rejected.
        """
        current = self.get(table_id)
        if current.conversation.closed:
            raise ValueError("table is closed")
        existing = next(
            (turn for turn in self._turns[table_id] if turn.message_id == message_id),
            None,
        )
        if existing is not None:
            if existing.participant_id != participant_id or existing.text != text:
                raise ValueError("message_id already belongs to different message")
            return current, False
        turn = HumanTurn(
            turn_id=max((item.turn_id for item in self._turns[table_id]), default=0) + 1,
            participant_id=participant_id,
            text=text,
            message_id=message_id,
        )
        state = observe_turn(current, turn)
        self._turns[table_id].append(turn)
        return self._append(table_id, state), True

    @_synchronized
    def close_table(self, table_id: str) -> TableState:
        """Mark a table closed exactly once after close artifacts are ready."""
        state = self.get(table_id)
        if state.conversation.closed:
            return state
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.phase = Phase.CLOSE
        updated.close_readiness = Level.HIGH
        updated.conversation.state = "closed"
        updated.conversation.closed = True
        updated.intervention.recommended_action = Action.SILENCE
        return self._append(table_id, updated)

    @_synchronized
    def append_intervention_state(self, table_id: str, state: TableState) -> TableState:
        """Commit the one follow-up snapshot produced by a real host intervention."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("intervention state must be the next snapshot for its table")
        return self._append(table_id, state)

    @_synchronized
    def append_intervention_bundle(
        self, table_id: str, state: TableState, record: InterventionRecord
    ) -> TableState:
        """Commit an intervention snapshot and its audit record together."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("intervention state must be the next snapshot for its table")
        if record.table_id != table_id or record.state_version != state.version:
            raise ValueError("intervention record must reference the new table state")
        if record.action is Action.SILENCE:
            raise ValueError("SILENCE interventions are not persisted")
        if any(item.intervention_id == record.intervention_id for item in self._interventions[table_id]):
            raise ValueError(f"intervention already exists: {record.intervention_id}")
        snapshot = TableState.model_validate(state.model_dump())
        self._states[table_id].append(snapshot)
        self._interventions[table_id].append(record.model_copy(deep=True))
        return snapshot.model_copy(deep=True)

    @_synchronized
    def append_intervention_record(self, table_id: str, record: InterventionRecord) -> None:
        """Persist one explainable non-SILENCE action without changing table state."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if record.table_id != table_id or record.state_version != latest.version:
            raise ValueError("intervention record must reference the current table state")
        if record.action is Action.SILENCE:
            raise ValueError("SILENCE interventions are not persisted")
        if any(item.intervention_id == record.intervention_id for item in self._interventions[table_id]):
            raise ValueError(f"intervention already exists: {record.intervention_id}")
        self._interventions[table_id].append(record.model_copy(deep=True))

    @_synchronized
    def update_intervention_record(self, table_id: str, record: InterventionRecord) -> InterventionRecord:
        """Replace an existing audit entry when post-intervention evidence arrives."""
        self.get(table_id)
        if record.table_id != table_id:
            raise ValueError("intervention record must belong to the table")
        if record.action is Action.SILENCE:
            raise ValueError("SILENCE interventions are not persisted")
        for index, existing in enumerate(self._interventions[table_id]):
            if existing.intervention_id == record.intervention_id:
                self._interventions[table_id][index] = record.model_copy(deep=True)
                return record.model_copy(deep=True)
        raise ValueError(f"unknown intervention: {record.intervention_id}")

    @_synchronized
    def interventions(self, table_id: str) -> list[InterventionRecord]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._interventions[table_id]]

    @_synchronized
    def append_safety_state(self, table_id: str, state: TableState) -> TableState:
        """Commit a safety-only snapshot without recording the intercepted human turn."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("safety state must be the next snapshot for its table")
        return self._append(table_id, state)

    @_synchronized
    def replay(self, table_id: str, from_version: int | None = None) -> list[TableState]:
        snapshots = sorted(self._states[table_id], key=lambda state: state.version)
        if from_version is not None:
            if not any(state.version == from_version for state in snapshots):
                raise ValueError(f"unknown state version: {from_version}")
            snapshots = [state for state in snapshots if state.version >= from_version]
        return [state.model_copy(deep=True) for state in snapshots]

    @_synchronized
    def turns(self, table_id: str) -> list[HumanTurn]:
        self.get(table_id)
        return [turn.model_copy(deep=True) for turn in self._turns[table_id]]

    @_synchronized
    def set_trusted_grounding_card(self, table_id: str, card: GroundingCard) -> None:
        """Stage one validated demo-injected source for the table's next GROUND action."""
        self.get(table_id)
        if not all(value.strip() for value in (card.title, card.excerpt, card.source_ref)):
            raise ValueError("grounding card title, excerpt, and source_ref must be non-empty")
        self._trusted_grounding_cards[table_id] = card.model_copy(deep=True)

    @_synchronized
    def take_trusted_grounding_card(self, table_id: str) -> GroundingCard | None:
        """Consume the staged source so it cannot be silently reused for later claims."""
        self.get(table_id)
        card = self._trusted_grounding_cards.pop(table_id, None)
        return card.model_copy(deep=True) if card is not None else None

    @_synchronized
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
            (
                self._states,
                self._turns,
                self._trusted_grounding_cards,
                self._interventions,
                self._invitations,
            ) = self._load()

    @_synchronized
    def create(
        self, table_id: str, core_question: str, participants: Sequence[ParticipantSeed]
    ) -> TableState:
        if table_id in self._states:
            raise ValueError(f"table already exists: {table_id}")
        state = build_initial_state(table_id, core_question, participants)
        states = {**self._states, table_id: [state]}
        turns = {**self._turns, table_id: []}
        interventions = {**self._interventions, table_id: []}
        invitations = {**self._invitations, table_id: []}
        self._commit(states, turns, self._trusted_grounding_cards, interventions, invitations)
        return state.model_copy(deep=True)

    @_synchronized
    def append_turn(self, table_id: str, turn: HumanTurn) -> TableState:
        committed = turn.model_copy(deep=True)
        current = self.get(table_id)
        if current.conversation.closed:
            raise ValueError("table is closed")
        state = observe_turn(current, committed)
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        turns = {**self._turns, table_id: [*self._turns[table_id], committed]}
        self._commit(states, turns, self._trusted_grounding_cards, self._interventions)
        return snapshot.model_copy(deep=True)

    @_synchronized
    def append_message_once(
        self, table_id: str, participant_id: str, text: str, message_id: str
    ) -> tuple[TableState, bool]:
        """Atomically commit one client message and persist the idempotency key."""
        current = self.get(table_id)
        if current.conversation.closed:
            raise ValueError("table is closed")
        existing = next(
            (turn for turn in self._turns[table_id] if turn.message_id == message_id),
            None,
        )
        if existing is not None:
            if existing.participant_id != participant_id or existing.text != text:
                raise ValueError("message_id already belongs to different message")
            return current, False
        turn = HumanTurn(
            turn_id=max((item.turn_id for item in self._turns[table_id]), default=0) + 1,
            participant_id=participant_id,
            text=text,
            message_id=message_id,
        )
        state = observe_turn(current, turn)
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        turns = {**self._turns, table_id: [*self._turns[table_id], turn]}
        self._commit(states, turns, self._trusted_grounding_cards, self._interventions)
        return snapshot.model_copy(deep=True), True

    @_synchronized
    def create_invitation(
        self, table_id: str, inviter_id: str, candidate: ParticipantSeed, reason: str
    ) -> Invitation:
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if inviter_id not in state.participants:
            raise ValueError("inviter must be a table participant")
        if candidate.participant_id in state.participants:
            raise ValueError("candidate is already a table participant")
        existing = self._invitations[table_id]
        if any(item.candidate.participant_id == candidate.participant_id for item in existing):
            raise ValueError("candidate already has an invitation for this table")
        invitation = Invitation(
            invitation_id=f"{table_id}:invite:{len(existing) + 1}",
            table_id=table_id,
            inviter_id=inviter_id,
            candidate=candidate,
            reason=reason,
        )
        invitations = {**self._invitations, table_id: [*existing, invitation]}
        self._commit(self._states, self._turns, self._trusted_grounding_cards, self._interventions, invitations)
        return invitation.model_copy(deep=True)

    @_synchronized
    def invitations(self, table_id: str) -> list[Invitation]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._invitations[table_id]]

    @_synchronized
    def respond_invitation(
        self, table_id: str, invitation_id: str, participant_id: str, accept: bool
    ) -> tuple[Invitation, TableState | None]:
        state = self.get(table_id)
        invitation = next(
            (item for item in self._invitations[table_id] if item.invitation_id == invitation_id),
            None,
        )
        if invitation is None:
            raise ValueError(f"unknown invitation: {invitation_id}")
        if invitation.candidate.participant_id != participant_id:
            raise PermissionError("only the invited participant may respond")
        requested = InvitationStatus.ACCEPTED if accept else InvitationStatus.DECLINED
        if invitation.status is not InvitationStatus.PENDING:
            if invitation.status is requested:
                return invitation.model_copy(deep=True), state if accept else None
            raise ValueError("invitation has already been resolved")
        if state.conversation.closed:
            raise ValueError("table is closed")
        updated_invitation = invitation.model_copy(update={"status": requested})
        index = self._invitations[table_id].index(invitation)
        invitations = {
            **self._invitations,
            table_id: [
                updated_invitation if item.invitation_id == invitation_id else item
                for item in self._invitations[table_id]
            ],
        }
        if not accept:
            self._commit(self._states, self._turns, self._trusted_grounding_cards, self._interventions, invitations)
            return updated_invitation.model_copy(deep=True), None
        if participant_id in state.participants:
            raise ValueError("candidate is already a table participant")
        updated_state = state.model_copy(deep=True)
        updated_state.version += 1
        seed = invitation.candidate
        updated_state.participants[participant_id] = ParticipantState(
            participant_id=participant_id,
            display_name=seed.display_name,
            role=seed.role,
            declared_position=seed.declared_position,
            unused_relevant_experience=seed.relevant_experience,
            engagement="low",
        )
        snapshot = TableState.model_validate(updated_state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        self._commit(states, self._turns, self._trusted_grounding_cards, self._interventions, invitations)
        return updated_invitation.model_copy(deep=True), snapshot.model_copy(deep=True)

    @_synchronized
    def append_intervention_record(self, table_id: str, record: InterventionRecord) -> None:
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if record.table_id != table_id or record.state_version != latest.version:
            raise ValueError("intervention record must reference the current table state")
        if record.action is Action.SILENCE:
            raise ValueError("SILENCE interventions are not persisted")
        if any(item.intervention_id == record.intervention_id for item in self._interventions[table_id]):
            raise ValueError(f"intervention already exists: {record.intervention_id}")
        interventions = {
            **self._interventions,
            table_id: [*self._interventions[table_id], record.model_copy(deep=True)],
        }
        self._commit(self._states, self._turns, self._trusted_grounding_cards, interventions)

    @_synchronized
    def update_intervention_record(self, table_id: str, record: InterventionRecord) -> InterventionRecord:
        self.get(table_id)
        if record.table_id != table_id:
            raise ValueError("intervention record must belong to the table")
        if record.action is Action.SILENCE:
            raise ValueError("SILENCE interventions are not persisted")
        if not any(item.intervention_id == record.intervention_id for item in self._interventions[table_id]):
            raise ValueError(f"unknown intervention: {record.intervention_id}")
        interventions = {
            **self._interventions,
            table_id: [
                record.model_copy(deep=True) if item.intervention_id == record.intervention_id else item
                for item in self._interventions[table_id]
            ],
        }
        self._commit(self._states, self._turns, self._trusted_grounding_cards, interventions)
        return record.model_copy(deep=True)

    @_synchronized
    def set_trusted_grounding_card(self, table_id: str, card: GroundingCard) -> None:
        """Stage a source and persist it before acknowledging the write."""
        self.get(table_id)
        if not all(value.strip() for value in (card.title, card.excerpt, card.source_ref)):
            raise ValueError("grounding card title, excerpt, and source_ref must be non-empty")
        cards = {**self._trusted_grounding_cards, table_id: card.model_copy(deep=True)}
        self._commit(self._states, self._turns, cards)

    @_synchronized
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

    @_synchronized
    def _append(self, table_id: str, state: TableState) -> TableState:
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        self._commit(states, self._turns, self._trusted_grounding_cards)
        return snapshot.model_copy(deep=True)

    @_synchronized
    def append_intervention_bundle(
        self, table_id: str, state: TableState, record: InterventionRecord
    ) -> TableState:
        """Persist the state and matching audit record in one JSON snapshot."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("intervention state must be the next snapshot for its table")
        if record.table_id != table_id or record.state_version != state.version:
            raise ValueError("intervention record must reference the new table state")
        if record.action is Action.SILENCE:
            raise ValueError("SILENCE interventions are not persisted")
        if any(item.intervention_id == record.intervention_id for item in self._interventions[table_id]):
            raise ValueError(f"intervention already exists: {record.intervention_id}")
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        interventions = {
            **self._interventions,
            table_id: [*self._interventions[table_id], record.model_copy(deep=True)],
        }
        self._commit(states, self._turns, self._trusted_grounding_cards, interventions)
        return snapshot.model_copy(deep=True)

    @_synchronized
    def _commit(
        self,
        states: dict[str, list[TableState]],
        turns: dict[str, list[HumanTurn]],
        trusted_grounding_cards: dict[str, GroundingCard] | None = None,
        interventions: dict[str, list[InterventionRecord]] | None = None,
        invitations: dict[str, list[Invitation]] | None = None,
    ) -> None:
        cards = trusted_grounding_cards if trusted_grounding_cards is not None else self._trusted_grounding_cards
        audit = interventions if interventions is not None else self._interventions
        invite_rows = invitations if invitations is not None else self._invitations
        payload = {
            "tables": {
                table_id: {
                    "states": [state.model_dump(mode="json") for state in snapshots],
                    "turns": [turn.model_dump(mode="json") for turn in turns[table_id]],
                    "interventions": [item.model_dump(mode="json") for item in audit[table_id]],
                    "invitations": [item.model_dump(mode="json") for item in invite_rows[table_id]],
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
        self._states, self._turns, self._interventions, self._invitations = states, turns, audit, invite_rows
        self._trusted_grounding_cards = {
            table_id: card.model_copy(deep=True) for table_id, card in cards.items()
        }

    def _load(self) -> tuple[
        dict[str, list[TableState]],
        dict[str, list[HumanTurn]],
        dict[str, GroundingCard],
        dict[str, list[InterventionRecord]],
        dict[str, list[Invitation]],
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
        interventions: dict[str, list[InterventionRecord]] = {}
        invitations: dict[str, list[Invitation]] = {}
        for table_id, table in payload["tables"].items():
            if (not isinstance(table_id, str) or not table_id or not isinstance(table, dict)
                    or set(table) not in (
                        {"states", "turns"},
                        {"states", "turns", "interventions"},
                        {"states", "turns", "interventions", "invitations"},
                    )):
                raise ValueError(f"invalid persistence file: malformed table {table_id!r}")
            try:
                snapshots = [TableState.model_validate(item) for item in table["states"]]
                messages = [HumanTurn.model_validate(item) for item in table["turns"]]
                audit = [InterventionRecord.model_validate(item) for item in table.get("interventions", [])]
                invites = [Invitation.model_validate(item) for item in table.get("invitations", [])]
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid persistence file: invalid data for table {table_id!r}") from error
            if not snapshots or any(state.table_id != table_id for state in snapshots):
                raise ValueError(f"invalid persistence file: incompatible states for table {table_id!r}")
            if [state.version for state in snapshots] != list(range(len(snapshots))):
                raise ValueError(f"invalid persistence file: incompatible versions for table {table_id!r}")
            if [turn.turn_id for turn in messages] != sorted({turn.turn_id for turn in messages}):
                raise ValueError(f"invalid persistence file: incompatible turns for table {table_id!r}")
            if any(record.table_id != table_id for record in audit):
                raise ValueError(f"invalid persistence file: incompatible interventions for table {table_id!r}")
            if len({record.intervention_id for record in audit}) != len(audit):
                raise ValueError(f"invalid persistence file: duplicate interventions for table {table_id!r}")
            if any(invitation.table_id != table_id for invitation in invites):
                raise ValueError(f"invalid persistence file: incompatible invitations for table {table_id!r}")
            if len({invitation.invitation_id for invitation in invites}) != len(invites):
                raise ValueError(f"invalid persistence file: duplicate invitations for table {table_id!r}")
            candidate_ids = [invitation.candidate.participant_id for invitation in invites]
            if len(set(candidate_ids)) != len(candidate_ids):
                raise ValueError(f"invalid persistence file: duplicate invitation candidates for table {table_id!r}")
            states[table_id] = snapshots
            turns[table_id] = messages
            interventions[table_id] = audit
            invitations[table_id] = invites
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
        return states, turns, cards, interventions, invitations
