"""Small repositories used by the first HTTP integration slice."""

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path
import tempfile
import time
from threading import RLock
from typing import Any

from app.domain import Action, ActionEchoEntry, AgentRunRecord, BehaviorEvent, CommentPromotion, ContentSignal, ConversationMode, FollowUpOutcome, GroundingCard, HumanTurn, Invitation, InvitationPreference, InvitationStatus, InterventionRecord, JoinRequest, Level, NoMatchPreference, ParticipantSeed, PeripheralComment, PersonalContextConsent, Phase, QuestionFootprintEntry, QuestionFootprintNextTable, RelationshipMemory, SafetyLevel, SafetyReport, SafetyReportStatusAudit, SafetyResolution, StageSummary, StageSummaryFeedback, TableState, ValueFeedback
from app.domain.schemas import DemoSession, ParticipantState, SimulationGeneration
from app.orchestrator import build_initial_state, build_personal_card, build_shared_baseline, observe_turn

MAX_TABLE_PARTICIPANTS = 5
MAX_PUBLIC_SOURCE_SIGNALS = 20
MAX_TABLE_LINEAGE_DEPTH = 10
MAX_QUESTION_FOOTPRINT_ITEMS = 50
MAX_QUESTION_FOOTPRINT_NEXT_TABLES = 3
MAX_ACTION_ECHO_ITEMS = 50
MAX_JOIN_REQUESTS_PER_TABLE = 50
MAX_SAFETY_STRIKES_PER_PARTICIPANT = 2
MAX_SAVED_TABLES_PER_PARTICIPANT = 100


def _validate_message_source(
    state: TableState, participant_id: str, source: str, expected_state_version: int | None,
) -> None:
    if expected_state_version is not None and state.version != expected_state_version:
        raise ValueError("stale message generation")
    simulated = state.demo is not None and participant_id in state.demo.simulated_participant_ids
    if simulated != (source == "simulated"):
        raise ValueError("message source does not match participant identity")


def _index_public_source_signals(
    signals: Sequence[ContentSignal] | None,
    origin_signal_ids: Sequence[str],
) -> dict[str, ContentSignal]:
    """Validate a bounded public snapshot without accepting private payloads."""
    rows = list(signals or [])
    if len(rows) > MAX_PUBLIC_SOURCE_SIGNALS:
        raise ValueError(f"public source snapshot cannot exceed {MAX_PUBLIC_SOURCE_SIGNALS} signals")
    ids = [signal.signal_id for signal in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("public source snapshot signal_id values must be unique")
    allowed = set(origin_signal_ids)
    if any(signal_id not in allowed for signal_id in ids):
        raise ValueError("public source snapshot must reference origin_signal_ids")
    return {signal.signal_id: signal.model_copy(deep=True) for signal in rows}


def _follow_up_behavior_event(
    outcome: FollowUpOutcome,
    state_version: int,
    previous: FollowUpOutcome | None,
) -> BehaviorEvent | None:
    """Build one transition-scoped behavior signal for a follow-up update."""
    if (
        previous is not None
        and previous.participant_id == outcome.participant_id
        and previous.status == outcome.status
    ):
        return None
    transition = (
        "initial"
        if previous is None or previous.participant_id != outcome.participant_id
        else f"{previous.status}-to-{outcome.status}"
    )
    return BehaviorEvent(
        event_id=(
            f"{outcome.table_id}:follow-up:{outcome.follow_up_index}:"
            f"{outcome.participant_id}:{transition}"
        ),
        participant_id=outcome.participant_id,
        event_type="follow_up_outcome",
        table_id=outcome.table_id,
        state_version=state_version,
        detail=f"status:{outcome.status}",
    )


def _validate_behavior_event_context(state: TableState, event: BehaviorEvent) -> None:
    """Reject behavior signals that contradict the table lifecycle or membership."""
    if event.event_type == "table_selected":
        return
    if event.participant_id not in state.participants:
        raise ValueError("behavior participant must be a table participant")
    if event.event_type in {"follow_up_outcome", "table_closed", "value_feedback_submitted"} and not state.conversation.closed:
        raise ValueError("closed-table behavior events require a closed table")
    if event.event_type == "relationship_saved":
        if not state.conversation.closed:
            raise ValueError("relationship_saved requires a closed table")
        if event.related_participant_id not in state.participants:
            raise ValueError("relationship target must be a table participant")


def _table_closed_behavior_event(
    table_id: str, participant_id: str, state_version: int
) -> BehaviorEvent:
    """Build the stable private behavior signal for an actor-initiated close."""
    return BehaviorEvent(
        event_id=f"{participant_id}:table-closed:{table_id}",
        participant_id=participant_id,
        event_type="table_closed",
        table_id=table_id,
        state_version=state_version,
        detail="closed",
    )


def _value_feedback_behavior_event(
    table_id: str, participant_id: str, state_version: int
) -> BehaviorEvent:
    """Build the stable private behavior signal for a first value reflection."""
    return BehaviorEvent(
        event_id=f"{participant_id}:value-feedback:{table_id}",
        participant_id=participant_id,
        event_type="value_feedback_submitted",
        table_id=table_id,
        state_version=state_version,
        detail="submitted",
    )


def _synchronized(method: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize one repository operation while allowing nested calls."""

    @wraps(method)
    def wrapped(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            # ``JsonTableRepository`` overrides these hooks to coordinate
            # multiple worker processes.  The in-memory implementation keeps
            # the same call shape but uses a no-op external scope.
            depth = getattr(self, "_operation_depth", 0)
            if depth:
                return method(self, *args, **kwargs)
            with self._external_lock():
                self._operation_depth = 1
                try:
                    self._before_operation()
                    return method(self, *args, **kwargs)
                finally:
                    self._operation_depth = 0

    return wrapped


class InMemoryTableRepository:
    """Store immutable state snapshots and committed human turns by table."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._operation_depth = 0
        self._states: dict[str, list[TableState]] = {}
        self._turns: dict[str, list[HumanTurn]] = {}
        self._interventions: dict[str, list[InterventionRecord]] = {}
        self._trusted_grounding_cards: dict[str, GroundingCard] = {}
        self._invitations: dict[str, list[Invitation]] = {}
        self._join_requests: dict[str, list[JoinRequest]] = {}
        self._follow_up_outcomes: dict[str, dict[int, FollowUpOutcome]] = {}
        self._value_feedback: dict[str, dict[str, ValueFeedback]] = {}
        self._comments: dict[str, list[PeripheralComment]] = {}
        self._comment_promotions: dict[str, list[CommentPromotion]] = {}
        self._no_match: dict[str, set[str]] = {}
        self._account_invitation_preferences: dict[str, InvitationPreference] = {}
        self._saved_tables: dict[str, list[str]] = {}
        self._safety_reports: dict[str, list[SafetyReport]] = {}
        self._safety_report_audits: dict[str, list[SafetyReportStatusAudit]] = {}
        self._safety_resolutions: dict[str, list[SafetyResolution]] = {}
        # Private escalation counters; never projected to table members.
        self._safety_strikes: dict[str, dict[str, int]] = {}
        self._personal_context_consents: dict[str, PersonalContextConsent] = {}
        self._behavior_events: dict[str, list[BehaviorEvent]] = {}
        self._public_source_signals: dict[str, dict[str, ContentSignal]] = {}
        self._stage_summaries: dict[str, list[StageSummary]] = {}
        self._summary_feedback: dict[str, list[StageSummaryFeedback]] = {}
        self._agent_runs: dict[str, list[AgentRunRecord]] = {}

    @contextmanager
    def _external_lock(self):
        """Hook for repositories that coordinate across worker processes."""

        yield

    def _before_operation(self) -> None:
        """Hook for refreshing state before a top-level repository call."""

        return None

    @_synchronized
    def create(
        self,
        table_id: str,
        core_question: str,
        participants: Sequence[ParticipantSeed],
        *,
        origin_table_id: str | None = None,
        origin_signal_ids: Sequence[str] | None = None,
        origin_signals: Sequence[ContentSignal] | None = None,
        demo: DemoSession | None = None,
    ) -> TableState:
        if table_id in self._states:
            raise ValueError(f"table already exists: {table_id}")
        if len(participants) > MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
        origin_ids = list(
            origin_signal_ids
            or [signal.signal_id for signal in (origin_signals or [])]
        )
        public_signals = _index_public_source_signals(origin_signals, origin_ids)
        participants = [
            self.apply_account_invitation_preference(seed)
            for seed in participants
        ]
        state = build_initial_state(
            table_id,
            core_question,
            participants,
            origin_table_id,
            origin_ids,
        )
        if demo is not None:
            if set(state.participants) != {demo.owner_participant_id, *demo.simulated_participant_ids}:
                raise ValueError("demo participants must match the owner and simulated identities")
            state.demo = demo.model_copy(deep=True)
        self._states[table_id] = [state]
        self._turns[table_id] = []
        self._interventions[table_id] = []
        self._invitations[table_id] = []
        self._join_requests[table_id] = []
        self._follow_up_outcomes[table_id] = {}
        self._value_feedback[table_id] = {}
        self._comments[table_id] = []
        self._comment_promotions[table_id] = []
        self._safety_reports[table_id] = []
        self._safety_report_audits[table_id] = []
        self._safety_resolutions[table_id] = []
        self._safety_strikes[table_id] = {}
        self._public_source_signals[table_id] = public_signals
        self._stage_summaries[table_id] = []
        self._summary_feedback[table_id] = []
        self._agent_runs[table_id] = []
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
            states = [
                state for state in states
                if not state.conversation.closed and not state.conversation.soft_expired
            ]
        return [state.model_copy(deep=True) for state in states]

    @_synchronized
    def add_participant(self, table_id: str, seed: ParticipantSeed) -> TableState:
        seed = self.apply_account_invitation_preference(seed)
        state = self.get(table_id)
        if state.demo is not None:
            raise ValueError("demo participants are fixed for this session")
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if seed.participant_id in state.participants:
            raise ValueError(f"participant already exists: {seed.participant_id}")
        if len(state.participants) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.participants[seed.participant_id] = ParticipantState(
            participant_id=seed.participant_id,
            display_name=seed.display_name,
            role=seed.role,
            roundtable_invite_preference=seed.roundtable_invite_preference,
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
        candidate = self.apply_account_invitation_preference(candidate)
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if inviter_id not in state.participants:
            raise ValueError("inviter must be a table participant")
        if self.is_no_match(inviter_id, candidate.participant_id):
            raise ValueError("participant has disabled matching with this candidate")
        if candidate.participant_id in state.participants:
            raise ValueError("candidate is already a table participant")
        if candidate.roundtable_invite_preference is InvitationPreference.NONE:
            raise ValueError("candidate has disabled roundtable invitations")
        if len(state.participants) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
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
    def create_join_request(self, request: JoinRequest) -> tuple[JoinRequest, bool]:
        """Persist one candidate request without granting a seat."""
        request = request.model_copy(update={
            "candidate": self.apply_account_invitation_preference(request.candidate),
        })
        state = self.get(request.table_id)
        if request.status != "pending" or request.invitation_id is not None:
            raise ValueError("new join requests must be pending")
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if request.candidate.participant_id in state.participants:
            raise ValueError("candidate is already a table participant")
        if len(state.participants) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
        if any(
            self.is_no_match(member_id, request.candidate.participant_id)
            for member_id in state.participants
        ):
            raise ValueError("participant has disabled matching with this table")
        existing = next(
            (
                item for item in self._join_requests[request.table_id]
                if item.request_id == request.request_id
            ),
            None,
        )
        if existing is not None:
            if existing.model_dump(mode="json") != request.model_dump(mode="json"):
                raise ValueError("request_id already belongs to a different join request")
            return existing.model_copy(deep=True), False
        if any(
            item.candidate.participant_id == request.candidate.participant_id
            for item in self._join_requests[request.table_id]
        ):
            raise ValueError("candidate already has a join request for this table")
        if len(self._join_requests[request.table_id]) >= MAX_JOIN_REQUESTS_PER_TABLE:
            raise ValueError(
                f"table cannot retain more than {MAX_JOIN_REQUESTS_PER_TABLE} join requests"
            )
        self._join_requests[request.table_id].append(request.model_copy(deep=True))
        return request.model_copy(deep=True), True

    @_synchronized
    def join_requests(self, table_id: str) -> list[JoinRequest]:
        """Return isolated join requests for application-level privacy projection."""
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._join_requests[table_id]]

    @_synchronized
    def approve_join_request(
        self, table_id: str, request_id: str, inviter_id: str, reason: str
    ) -> tuple[JoinRequest, Invitation]:
        """Approve a request by creating an invitation, never a direct seat."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if inviter_id not in state.participants:
            raise ValueError("inviter must be a table participant")
        if not reason.strip():
            raise ValueError("invitation reason must be non-empty")
        request = next(
            (item for item in self._join_requests[table_id] if item.request_id == request_id),
            None,
        )
        if request is None:
            raise KeyError(f"unknown join request: {request_id}")
        if request.status == "invited":
            invitation = next(
                (
                    item for item in self._invitations[table_id]
                    if item.invitation_id == request.invitation_id
                ),
                None,
            )
            if invitation is None:
                raise ValueError("join request invitation is missing")
            return request.model_copy(deep=True), invitation.model_copy(deep=True)
        if request.status == "declined":
            raise ValueError("join request has already been declined")
        candidate = request.candidate
        if candidate.participant_id in state.participants:
            raise ValueError("candidate is already a table participant")
        if len(state.participants) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
        if self.is_no_match(inviter_id, candidate.participant_id):
            raise ValueError("participant has disabled matching with this candidate")
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
            reason=reason.strip(),
        )
        updated_request = request.model_copy(update={
            "status": "invited",
            "invitation_id": invitation.invitation_id,
        })
        index = self._join_requests[table_id].index(request)
        self._join_requests[table_id][index] = updated_request
        self._invitations[table_id].append(invitation)
        return updated_request.model_copy(deep=True), invitation.model_copy(deep=True)

    @_synchronized
    def decline_join_request(
        self, table_id: str, request_id: str, member_id: str
    ) -> JoinRequest:
        """Decline a pending request; repeated decline remains idempotent."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if member_id not in state.participants:
            raise ValueError("member must be a table participant")
        request = next(
            (item for item in self._join_requests[table_id] if item.request_id == request_id),
            None,
        )
        if request is None:
            raise KeyError(f"unknown join request: {request_id}")
        if request.status == "invited":
            raise ValueError("invited join requests cannot be declined")
        if request.status == "declined":
            return request.model_copy(deep=True)
        updated = request.model_copy(update={"status": "declined"})
        self._join_requests[table_id][self._join_requests[table_id].index(request)] = updated
        return updated.model_copy(deep=True)

    @_synchronized
    def set_no_match(self, participant_id: str, blocked_participant_id: str) -> NoMatchPreference:
        """Persist a self-scoped, symmetric no-match preference."""
        preference = NoMatchPreference(
            participant_id=participant_id,
            blocked_participant_id=blocked_participant_id,
        )
        rows = {owner: set(targets) for owner, targets in self._no_match.items()}
        rows.setdefault(participant_id, set()).add(blocked_participant_id)
        self._no_match = rows
        return preference

    @_synchronized
    def remove_no_match(self, participant_id: str, blocked_participant_id: str) -> bool:
        """Remove one preference; repeated deletes are idempotent."""
        if not participant_id.strip() or not blocked_participant_id.strip():
            raise ValueError("participant ids must be non-empty")
        targets = self._no_match.get(participant_id)
        if not targets or blocked_participant_id not in targets:
            return False
        rows = {owner: set(values) for owner, values in self._no_match.items()}
        rows[participant_id].remove(blocked_participant_id)
        if not rows[participant_id]:
            rows.pop(participant_id)
        self._no_match = rows
        return True

    @_synchronized
    def no_match_preferences(self, participant_id: str) -> list[NoMatchPreference]:
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        return [
            NoMatchPreference(participant_id=participant_id, blocked_participant_id=target)
            for target in sorted(self._no_match.get(participant_id, set()))
        ]

    @_synchronized
    def is_no_match(self, participant_id: str, other_participant_id: str) -> bool:
        if not participant_id.strip() or not other_participant_id.strip():
            return False
        return (
            other_participant_id in self._no_match.get(participant_id, set())
            or participant_id in self._no_match.get(other_participant_id, set())
        )

    @_synchronized
    def account_invitation_preference(
        self, participant_id: str
    ) -> InvitationPreference | None:
        """Return an explicitly saved account preference, if one exists."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        return self._account_invitation_preferences.get(participant_id)

    @_synchronized
    def set_account_invitation_preference(
        self, participant_id: str, preference: InvitationPreference
    ) -> InvitationPreference:
        """Persist a self-scoped preference for future matching and invitations."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        self._account_invitation_preferences = {
            **self._account_invitation_preferences,
            participant_id: preference,
        }
        return preference

    @_synchronized
    def apply_account_invitation_preference(
        self, seed: ParticipantSeed
    ) -> ParticipantSeed:
        """Overlay an explicit account preference on a possibly stale source seed."""
        preference = self._account_invitation_preferences.get(seed.participant_id)
        if preference is None or preference is seed.roundtable_invite_preference:
            return seed.model_copy(deep=True)
        return seed.model_copy(update={"roundtable_invite_preference": preference}, deep=True)

    @_synchronized
    def save_table(self, participant_id: str, table_id: str) -> bool:
        """Save one existing table privately; repeated saves are idempotent."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        self.get(table_id)
        existing = self._saved_tables.get(participant_id, [])
        if table_id in existing:
            return False
        if len(existing) >= MAX_SAVED_TABLES_PER_PARTICIPANT:
            raise ValueError(
                f"saved tables cannot exceed {MAX_SAVED_TABLES_PER_PARTICIPANT}"
            )
        self._saved_tables = {
            **self._saved_tables,
            participant_id: [*existing, table_id],
        }
        return True

    @_synchronized
    def unsave_table(self, participant_id: str, table_id: str) -> bool:
        """Remove one private saved table; repeated removals are idempotent."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        self.get(table_id)
        existing = self._saved_tables.get(participant_id, [])
        if table_id not in existing:
            return False
        remaining = [item for item in existing if item != table_id]
        rows = {**self._saved_tables}
        if remaining:
            rows[participant_id] = remaining
        else:
            rows.pop(participant_id)
        self._saved_tables = rows
        return True

    @_synchronized
    def saved_table_ids(self, participant_id: str) -> list[str]:
        """Return private saved table IDs in most-recently-saved-first order."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        return list(reversed(self._saved_tables.get(participant_id, [])))

    @_synchronized
    def record_safety_report(self, report: SafetyReport) -> tuple[SafetyReport, bool]:
        """Store one member report without changing the table conversation."""
        state = self.get(report.table_id)
        if report.state_version != state.version:
            raise ValueError("safety report must reference the current table state")
        if report.reporter_id not in state.participants:
            raise ValueError("reporter must be a table participant")
        if report.target_participant_id not in state.participants:
            raise ValueError("target must be a table participant")
        existing = next(
            (item for item in self._safety_reports[report.table_id] if item.report_id == report.report_id),
            None,
        )
        if existing is not None:
            if existing.model_dump(mode="json") != report.model_dump(mode="json"):
                raise ValueError("report_id already belongs to a different report")
            return existing.model_copy(deep=True), False
        self._safety_reports[report.table_id].append(report.model_copy(deep=True))
        return report.model_copy(deep=True), True

    @_synchronized
    def safety_reports(
        self,
        table_id: str,
        reporter_id: str | None = None,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[SafetyReport]:
        """Return reports; callers must apply the public reporter visibility boundary."""
        self.get(table_id)
        if status is not None and status not in {"open", "acknowledged", "resolved"}:
            raise ValueError("unsupported safety report status filter")
        if offset < 0 or (limit is not None and limit < 1):
            raise ValueError("safety report pagination must be non-negative")
        rows = self._safety_reports[table_id]
        if reporter_id is not None:
            rows = [item for item in rows if item.reporter_id == reporter_id]
        if status is not None:
            rows = [item for item in rows if item.status == status]
        if limit is not None:
            rows = rows[offset:offset + limit]
        elif offset:
            rows = rows[offset:]
        return [item.model_copy(deep=True) for item in rows]

    @_synchronized
    def safety_report_audits(
        self, table_id: str, report_id: str | None = None
    ) -> list[SafetyReportStatusAudit]:
        """Return trusted report status history for the moderation adapter."""
        self.get(table_id)
        rows = self._safety_report_audits[table_id]
        if report_id is not None:
            rows = [item for item in rows if item.report_id == report_id]
        return [item.model_copy(deep=True) for item in rows]

    @_synchronized
    def update_safety_report_status(
        self,
        table_id: str,
        report_id: str,
        status: str,
        *,
        moderator_id: str = "system",
        reason: str | None = None,
    ) -> SafetyReport:
        """Advance one private report through the moderator status lifecycle."""
        self.get(table_id)
        if status not in {"acknowledged", "resolved"}:
            raise ValueError("unsupported safety report status")
        if not moderator_id.strip():
            raise ValueError("moderator_id must be non-empty")
        for index, report in enumerate(self._safety_reports[table_id]):
            if report.report_id != report_id:
                continue
            if report.status == status:
                return report.model_copy(deep=True)
            allowed = {
                "open": {"acknowledged", "resolved"},
                "acknowledged": {"resolved"},
                "resolved": set(),
            }
            if status not in allowed[report.status]:
                raise ValueError("safety report status cannot move backwards")
            updated = report.model_copy(update={"status": status})
            self._safety_reports[table_id][index] = updated
            self._safety_report_audits[table_id].append(SafetyReportStatusAudit(
                event_id=f"{table_id}:{report_id}:{status}",
                table_id=table_id,
                report_id=report_id,
                moderator_id=moderator_id.strip(),
                from_status=report.status,
                to_status=status,
                reason=reason.strip() if reason is not None and reason.strip() else None,
            ))
            return updated.model_copy(deep=True)
        raise KeyError(f"unknown safety report: {report_id}")

    @_synchronized
    def safety_resolutions(self, table_id: str) -> list[SafetyResolution]:
        """Return immutable moderator decisions for controlled review."""
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._safety_resolutions[table_id]]

    @_synchronized
    def safety_strike_count(self, table_id: str, participant_id: str) -> int:
        """Read the private boundary-violation count for one table member."""
        self.get(table_id)
        return self._safety_strikes.get(table_id, {}).get(participant_id, 0)

    @_synchronized
    def record_safety_strike(self, table_id: str, participant_id: str) -> int:
        """Increment a bounded private safety strike counter for one actor."""
        self.get(table_id)
        if not participant_id.strip():
            raise ValueError("safety strike actor must be non-empty")
        counts = dict(self._safety_strikes.setdefault(table_id, {}))
        current = counts.get(participant_id, 0)
        if current == 0 and len(counts) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError("safety strike ledger is full")
        if current < MAX_SAFETY_STRIKES_PER_PARTICIPANT:
            counts[participant_id] = current + 1
            self._safety_strikes[table_id] = counts
        return counts.get(participant_id, current)

    @_synchronized
    def resolve_safety(
        self,
        table_id: str,
        action: str,
        moderator_id: str,
        reason: str,
        participant_id: str | None = None,
    ) -> tuple[TableState, SafetyResolution]:
        """Atomically resume a paused table or remove one offending member."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if state.conversation.safety_level is not SafetyLevel.CRITICAL:
            raise ValueError("table is not paused for safety review")
        if action not in {"resume", "remove_participant"}:
            raise ValueError("unsupported safety resolution action")
        if not moderator_id.strip() or not reason.strip():
            raise ValueError("moderator_id and reason must be non-empty")
        if action == "resume" and participant_id is not None:
            raise ValueError("resume must not include participant_id")
        if action == "remove_participant":
            if not participant_id or participant_id not in state.participants:
                raise ValueError("participant_id must be a current table participant")

        updated = state.model_copy(deep=True)
        updated.version += 1
        if action == "remove_participant":
            del updated.participants[participant_id]  # type: ignore[index]
        updated.conversation.safety_level = SafetyLevel.NORMAL
        updated.conversation.state = (
            "sync_active" if updated.conversation.mode is ConversationMode.SYNC else "active"
        )
        updated.intervention.recommended_action = Action.SILENCE
        updated.agent.status = "active"
        committed = self._append(table_id, updated)
        resolution = SafetyResolution(
            resolution_id=f"{table_id}:safety-resolution:{committed.version}",
            table_id=table_id,
            action=action,
            moderator_id=moderator_id.strip(),
            participant_id=participant_id,
            reason=reason.strip(),
            from_state_version=state.version,
            state_version=committed.version,
        )
        self._safety_resolutions[table_id].append(resolution.model_copy(deep=True))
        return committed, resolution

    @_synchronized
    def set_personal_context_consent(
        self, consent: PersonalContextConsent
    ) -> PersonalContextConsent:
        self._personal_context_consents[consent.viewer_id] = consent.model_copy(deep=True)
        return consent.model_copy(deep=True)

    @_synchronized
    def revoke_personal_context_consent(self, viewer_id: str) -> bool:
        if not viewer_id.strip():
            raise ValueError("viewer_id must be non-empty")
        if viewer_id not in self._personal_context_consents:
            return False
        self._personal_context_consents.pop(viewer_id)
        return True

    @_synchronized
    def personal_context_consent(
        self, viewer_id: str
    ) -> PersonalContextConsent | None:
        if not viewer_id.strip():
            raise ValueError("viewer_id must be non-empty")
        consent = self._personal_context_consents.get(viewer_id)
        return consent.model_copy(deep=True) if consent is not None else None

    @_synchronized
    def invitations(self, table_id: str) -> list[Invitation]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._invitations[table_id]]

    @_synchronized
    def participant_invitations(
        self,
        participant_id: str,
        status: InvitationStatus | None = None,
    ) -> list[Invitation]:
        """Return one candidate's invitations across tables in stable inbox order."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        status_order = {
            InvitationStatus.PENDING: 0,
            InvitationStatus.ACCEPTED: 1,
            InvitationStatus.DECLINED: 2,
        }
        rows = [
            invitation
            for invitations in self._invitations.values()
            for invitation in invitations
            if invitation.candidate.participant_id == participant_id
            and (status is None or invitation.status is status)
        ]
        rows.sort(key=lambda item: (
            status_order[item.status],
            item.table_id,
            item.invitation_id,
        ))
        return [item.model_copy(deep=True) for item in rows]

    @_synchronized
    def record_follow_up_outcome(self, outcome: FollowUpOutcome) -> FollowUpOutcome:
        """Upsert one participant-reported result after a table closes."""
        state = self.get(outcome.table_id)
        if not state.conversation.closed:
            raise ValueError("follow-up outcomes require a closed table")
        if outcome.participant_id not in state.participants:
            raise ValueError(f"unknown participant: {outcome.participant_id}")
        table_outcomes = self._follow_up_outcomes[outcome.table_id]
        previous = table_outcomes.get(outcome.follow_up_index)
        table_outcomes[outcome.follow_up_index] = outcome.model_copy(deep=True)
        event = _follow_up_behavior_event(outcome, state.version, previous)
        if event is not None:
            self._behavior_events.setdefault(outcome.participant_id, []).append(event)
        return outcome.model_copy(deep=True)

    @_synchronized
    def follow_up_outcomes(self, table_id: str) -> list[FollowUpOutcome]:
        self.get(table_id)
        return [
            self._follow_up_outcomes[table_id][index].model_copy(deep=True)
            for index in sorted(self._follow_up_outcomes[table_id])
        ]

    @_synchronized
    def record_value_feedback(self, feedback: ValueFeedback) -> ValueFeedback:
        """Upsert one participant's private post-close value reflection."""
        state = self.get(feedback.table_id)
        if not state.conversation.closed:
            raise ValueError("value feedback requires a closed table")
        if feedback.state_version != state.version:
            raise ValueError("value feedback must reference the current closed state")
        if feedback.participant_id not in state.participants:
            raise ValueError(f"unknown participant: {feedback.participant_id}")
        behavior_event = _value_feedback_behavior_event(
            feedback.table_id, feedback.participant_id, state.version
        )
        existing_event = next(
            (
                item
                for item in self._behavior_events.get(feedback.participant_id, [])
                if item.event_id == behavior_event.event_id
            ),
            None,
        )
        if existing_event is not None and existing_event.model_dump(mode="json") != behavior_event.model_dump(mode="json"):
            raise ValueError("event_id already belongs to a different behavior event")
        self._value_feedback[feedback.table_id][feedback.participant_id] = feedback.model_copy(deep=True)
        if existing_event is None:
            self._behavior_events.setdefault(feedback.participant_id, []).append(behavior_event)
        return feedback.model_copy(deep=True)

    @_synchronized
    def value_feedback(self, table_id: str) -> list[ValueFeedback]:
        self.get(table_id)
        return [
            self._value_feedback[table_id][participant_id].model_copy(deep=True)
            for participant_id in sorted(self._value_feedback[table_id])
        ]

    @_synchronized
    def append_comment_once(self, comment: PeripheralComment) -> tuple[PeripheralComment, bool]:
        """Persist one public peripheral comment with table-scoped idempotency."""
        state = self.get(comment.table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if comment.state_version != state.version:
            raise ValueError("comment must reference the current table state")
        existing = next(
            (item for item in self._comments[comment.table_id] if item.comment_id == comment.comment_id),
            None,
        )
        if existing is not None:
            if existing.author_id != comment.author_id or existing.text != comment.text:
                raise ValueError("comment_id already belongs to different comment")
            return existing.model_copy(deep=True), False
        self._comments[comment.table_id].append(comment.model_copy(deep=True))
        return comment.model_copy(deep=True), True

    @_synchronized
    def comments(self, table_id: str) -> list[PeripheralComment]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._comments[table_id]]

    @_synchronized
    def promote_comment_once(
        self,
        table_id: str,
        comment_id: str,
        promoter_id: str,
        *,
        expected_state_version: int | None = None,
    ) -> tuple[CommentPromotion, TableState, bool]:
        """Promote one comment into a responsible core-member turn atomically."""
        current = self.get(table_id)
        if current.conversation.closed:
            raise ValueError("table is closed")
        if current.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        existing = next(
            (item for item in self._comment_promotions[table_id] if item.comment_id == comment_id),
            None,
        )
        if existing is not None:
            if existing.promoter_id != promoter_id:
                raise ValueError("comment_id is already promoted by another participant")
            return existing.model_copy(deep=True), current, False
        if promoter_id not in current.participants:
            raise PermissionError("promoter must be a table participant")
        if expected_state_version is not None and current.version != expected_state_version:
            raise ValueError("table changed; retry comment promotion")
        comment = next(
            (item for item in self._comments[table_id] if item.comment_id == comment_id),
            None,
        )
        if comment is None:
            raise KeyError(f"unknown comment: {comment_id}")
        turn_id = max((item.turn_id for item in self._turns[table_id]), default=0) + 1
        message_id = f"{table_id}:comment:{comment_id}"
        turn = HumanTurn(
            turn_id=turn_id,
            participant_id=promoter_id,
            text=comment.text,
            message_id=message_id,
            source_comment_id=comment.comment_id,
        )
        state = observe_turn(current, turn)
        promotion = CommentPromotion(
            promotion_id=f"{table_id}:comment-promotion:{comment_id}",
            table_id=table_id,
            comment_id=comment.comment_id,
            promoter_id=promoter_id,
            turn_id=turn.turn_id,
            state_version=state.version,
            message_id=message_id,
        )
        self._turns[table_id].append(turn)
        self._comment_promotions[table_id].append(promotion)
        self._behavior_events.setdefault(promoter_id, []).append(BehaviorEvent(
            event_id=f"{table_id}:human:{message_id}",
            participant_id=promoter_id,
            event_type="human_message",
            table_id=table_id,
            state_version=state.version,
        ))
        return promotion.model_copy(deep=True), self._append(table_id, state), True

    @_synchronized
    def comment_promotions(self, table_id: str) -> list[CommentPromotion]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._comment_promotions[table_id]]

    @_synchronized
    def record_table_closed_behavior(
        self, table_id: str, participant_id: str
    ) -> tuple[BehaviorEvent, bool]:
        """Record the actor's close action after an evidence-backed close."""
        state = self.get(table_id)
        if not state.conversation.closed:
            raise ValueError("table_closed behavior requires a closed table")
        if participant_id not in state.participants:
            raise ValueError("close actor must be a table participant")
        return self._record_behavior_event(
            _table_closed_behavior_event(table_id, participant_id, state.version)
        )

    @_synchronized
    def record_behavior_event(self, event: BehaviorEvent) -> tuple[BehaviorEvent, bool]:
        """Persist one bounded product behavior signal with user-scoped idempotency."""
        if event.event_type in {"table_closed", "value_feedback_submitted"}:
            raise ValueError("server-generated behavior events require a dedicated repository path")
        return self._record_behavior_event(event)

    def _record_behavior_event(self, event: BehaviorEvent) -> tuple[BehaviorEvent, bool]:
        """Persist a validated event for public or dedicated repository paths."""
        state = self.get(event.table_id)
        _validate_behavior_event_context(state, event)
        if event.state_version is not None and event.state_version > state.version:
            raise ValueError("behavior event cannot reference a future state version")
        existing = next(
            (item for item in self._behavior_events.get(event.participant_id, []) if item.event_id == event.event_id),
            None,
        )
        if existing is not None:
            if existing.model_dump(mode="json") != event.model_dump(mode="json"):
                raise ValueError("event_id already belongs to a different behavior event")
            return existing.model_copy(deep=True), False
        self._behavior_events.setdefault(event.participant_id, []).append(event.model_copy(deep=True))
        return event.model_copy(deep=True), True

    @_synchronized
    def behavior_events(self, participant_id: str) -> list[BehaviorEvent]:
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        return [item.model_copy(deep=True) for item in self._behavior_events.get(participant_id, [])]

    @_synchronized
    def public_source_signals(self, table_id: str) -> list[ContentSignal]:
        """Return the public snapshots attached to a table's origin IDs."""
        state = self.get(table_id)
        snapshots = self._public_source_signals.get(table_id, {})
        return [
            snapshots[signal_id].model_copy(deep=True)
            for signal_id in state.origin_signal_ids
            if signal_id in snapshots
        ]

    @_synchronized
    def clear_behavior_events(self, participant_id: str) -> bool:
        """Clear one participant's private behavior ledger without touching table facts."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        return self._behavior_events.pop(participant_id, None) is not None

    @_synchronized
    def relationship_memories(self, participant_id: str) -> list[RelationshipMemory]:
        """Derive self-only relationship reminders from closed table snapshots."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        memories: list[RelationshipMemory] = []
        for table_id in sorted(self._states):
            state = self._states[table_id][-1]
            if not state.conversation.closed or participant_id not in state.participants:
                continue
            card = build_personal_card(state, participant_id)
            for relationship in card.worth_continuing_with:
                if state.demo is not None and relationship.participant_id in state.demo.simulated_participant_ids:
                    continue
                other = state.participants.get(relationship.participant_id)
                if other is None:
                    continue
                memories.append(RelationshipMemory(
                    table_id=table_id,
                    state_version=state.version,
                    core_question=state.core_question,
                    participant_id=other.participant_id,
                    display_name=other.display_name,
                    reason=relationship.reason,
                    evidence_turns=list(relationship.evidence_turns),
                ))
        return [memory.model_copy(deep=True) for memory in memories]

    @_synchronized
    def question_footprint(
        self, participant_id: str, *, limit: int = 20
    ) -> list[QuestionFootprintEntry]:
        """Derive a bounded self-only contribution history from closed states."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        if limit < 1 or limit > MAX_QUESTION_FOOTPRINT_ITEMS:
            raise ValueError(
                f"question footprint limit must be between 1 and {MAX_QUESTION_FOOTPRINT_ITEMS}"
            )
        entries: list[QuestionFootprintEntry] = []
        for table_id in sorted(self._states):
            state = self._states[table_id][-1]
            if not state.conversation.closed or participant_id not in state.participants:
                continue
            card = build_personal_card(state, participant_id)
            next_tables: list[QuestionFootprintNextTable] = []
            for child_id in sorted(self._states):
                child = self._states[child_id][-1]
                if child.origin_table_id != table_id:
                    continue
                next_tables.append(QuestionFootprintNextTable(
                    table_id=child.table_id,
                    state_version=child.version,
                    core_question=child.core_question,
                    phase=child.phase,
                    closed=child.conversation.closed,
                ))
                if len(next_tables) >= MAX_QUESTION_FOOTPRINT_NEXT_TABLES:
                    break
            entries.append(QuestionFootprintEntry(
                table_id=table_id,
                state_version=state.version,
                core_question=state.core_question,
                your_contribution=list(card.your_contribution),
                what_changed=list(card.what_changed),
                next_tables=next_tables,
            ))
            if len(entries) >= limit:
                break
        return [entry.model_copy(deep=True) for entry in entries]

    @_synchronized
    def action_echoes(self, participant_id: str, *, limit: int = 20) -> list[ActionEchoEntry]:
        """Derive a bounded history of this member's own follow-up actions."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        if limit < 1 or limit > MAX_ACTION_ECHO_ITEMS:
            raise ValueError(
                f"action echoes limit must be between 1 and {MAX_ACTION_ECHO_ITEMS}"
            )
        entries: list[ActionEchoEntry] = []
        for table_id in sorted(self._states):
            state = self._states[table_id][-1]
            if not state.conversation.closed or participant_id not in state.participants:
                continue
            try:
                items = build_shared_baseline(state, turns=self._turns[table_id]).collective_next_steps
            except ValueError:
                continue
            outcomes = self._follow_up_outcomes[table_id]
            for index, item in enumerate(items):
                outcome = outcomes.get(index)
                owned_commitment = item.is_commitment and item.owner_participant_id == participant_id
                reported_suggestion = (
                    not item.is_commitment
                    and outcome is not None
                    and outcome.participant_id == participant_id
                )
                if not owned_commitment and not reported_suggestion:
                    continue
                own_outcome = outcome if outcome is not None and outcome.participant_id == participant_id else None
                entries.append(ActionEchoEntry(
                    table_id=table_id,
                    state_version=state.version,
                    core_question=state.core_question,
                    follow_up_index=index,
                    item_type=item.item_type,
                    text=item.text,
                    evidence_turns=list(item.evidence_turns),
                    status=own_outcome.status if own_outcome is not None else None,
                    note=own_outcome.note if own_outcome is not None else None,
                ))
                if len(entries) >= limit:
                    return [entry.model_copy(deep=True) for entry in entries]
        return [entry.model_copy(deep=True) for entry in entries]

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
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if accept and any(
            self.is_no_match(member_id, participant_id)
            for member_id in state.participants
        ):
            raise ValueError("participant has disabled matching with this table")
        if accept and len(state.participants) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
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
            roundtable_invite_preference=seed.roundtable_invite_preference,
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
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
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
    def set_invitation_preference(
        self,
        table_id: str,
        participant_id: str,
        preference: InvitationPreference,
    ) -> TableState:
        """Set a participant's self-scoped roundtable invitation preference."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        participant = state.participants.get(participant_id)
        if participant is None:
            raise ValueError(f"unknown participant: {participant_id}")
        if participant.roundtable_invite_preference is preference:
            return state
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.participants[participant_id].roundtable_invite_preference = preference
        return self._append(table_id, updated)

    @_synchronized
    def upgrade_to_sync(
        self, table_id: str, *, sync_expires_at: float | None = None
    ) -> TableState:
        """Atomically switch an eligible table from async to sync mode."""
        state = self.get(table_id)
        if state.conversation.mode is ConversationMode.SYNC:
            return state
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if state.conversation.safety_level is SafetyLevel.CRITICAL:
            raise ValueError("table is paused for safety review")
        if sync_expires_at is not None and sync_expires_at <= 0:
            raise ValueError("sync_expires_at must be positive")
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.conversation.mode = ConversationMode.SYNC
        updated.conversation.state = "sync_active"
        updated.conversation.sync_expires_at = sync_expires_at
        return self._append(table_id, updated)

    @_synchronized
    def expire_sync_if_due(
        self, table_id: str, *, now: float | None = None
    ) -> tuple[TableState, bool]:
        """Lazily close an expired sync window and preserve its state snapshot."""
        state = self.get(table_id)
        expires_at = state.conversation.sync_expires_at
        if (
            state.conversation.mode is not ConversationMode.SYNC
            or expires_at is None
            or expires_at > (time.time() if now is None else now)
        ):
            return state, False
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.conversation.mode = ConversationMode.ASYNC
        updated.conversation.sync_expires_at = None
        if updated.conversation.safety_level is not SafetyLevel.CRITICAL:
            updated.conversation.state = "active"
        return self._append(table_id, updated), True

    @_synchronized
    def append_turn(self, table_id: str, turn: HumanTurn) -> TableState:
        """Commit a human turn; the WebSocket adapter will use this helper later."""
        current = self.get(table_id)
        if current.conversation.closed:
            raise ValueError("table is closed")
        if current.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        committed = turn.model_copy(deep=True)
        state = observe_turn(current, committed)
        self._turns[table_id].append(committed)
        self._behavior_events.setdefault(committed.participant_id, []).append(BehaviorEvent(
            event_id=f"{table_id}:human:{committed.message_id or committed.turn_id}",
            participant_id=committed.participant_id,
            event_type="human_message",
            table_id=table_id,
            state_version=state.version,
        ))
        return self._append(table_id, state)

    @_synchronized
    def append_message_once(
        self, table_id: str, participant_id: str, text: str, message_id: str,
        *, source: str = "human", generation: SimulationGeneration | None = None,
        expected_state_version: int | None = None,
    ) -> tuple[TableState, bool]:
        """Atomically commit one client message, returning ``(state, created)``.

        WebSocket clients may retry after a lost acknowledgement.  The message id
        is scoped to a table: an exact retry is acknowledged as already committed,
        while reusing an id for different content is rejected.
        """
        current = self.get(table_id)
        _validate_message_source(current, participant_id, source, expected_state_version)
        if current.conversation.closed:
            raise ValueError("table is closed")
        if current.conversation.soft_expired:
            raise ValueError("table is soft-expired")
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
            source=source,
            generation=generation,
        )
        state = observe_turn(current, turn)
        self._turns[table_id].append(turn)
        self._behavior_events.setdefault(participant_id, []).append(BehaviorEvent(
            event_id=f"{table_id}:human:{message_id}",
            participant_id=participant_id,
            event_type="human_message",
            table_id=table_id,
            state_version=state.version,
        ))
        return self._append(table_id, state), True

    @_synchronized
    def soft_expire_table(self, table_id: str, reason: str) -> TableState:
        """Hide a stale table from discovery while preserving its history."""
        state = self.get(table_id)
        if not reason.strip():
            raise ValueError("soft-expiry reason must be non-empty")
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            return state
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.conversation.soft_expired = True
        updated.conversation.state = "soft_expired"
        updated.conversation.soft_expiry_reason = reason.strip()
        updated.intervention.recommended_action = Action.SILENCE
        updated.agent.status = "paused"
        return self._append(table_id, updated)

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
        updated.agent.status = "closed"
        return self._append(table_id, updated)

    @_synchronized
    def close_table_for_participant(self, table_id: str, participant_id: str) -> TableState:
        """Atomically persist an actor close snapshot and its private behavior event."""
        state = self.get(table_id)
        if participant_id not in state.participants:
            raise ValueError("close actor must be a table participant")
        if state.conversation.closed:
            self.record_table_closed_behavior(table_id, participant_id)
            return state
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.phase = Phase.CLOSE
        updated.close_readiness = Level.HIGH
        updated.conversation.state = "closed"
        updated.conversation.closed = True
        updated.intervention.recommended_action = Action.SILENCE
        updated.agent.status = "closed"
        snapshot = TableState.model_validate(updated.model_dump())
        event = _table_closed_behavior_event(table_id, participant_id, snapshot.version)
        self._states[table_id].append(snapshot)
        self._behavior_events[participant_id] = [
            *self._behavior_events.get(participant_id, []), event
        ]
        return snapshot.model_copy(deep=True)

    @_synchronized
    def append_intervention_state(self, table_id: str, state: TableState) -> TableState:
        """Commit the one follow-up snapshot produced by a real host intervention."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if latest.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("intervention state must be the next snapshot for its table")
        return self._append(table_id, state)

    @_synchronized
    def append_intervention_bundle(
        self,
        table_id: str,
        state: TableState,
        record: InterventionRecord,
        *,
        consume_grounding_card: bool = False,
    ) -> TableState:
        """Commit an intervention snapshot, audit record, and optional card consumption."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if latest.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("intervention state must be the next snapshot for its table")
        if record.table_id != table_id or record.state_version != state.version:
            raise ValueError("intervention record must reference the new table state")
        if record.action is Action.SILENCE:
            raise ValueError("SILENCE interventions are not persisted")
        if any(item.intervention_id == record.intervention_id for item in self._interventions[table_id]):
            raise ValueError(f"intervention already exists: {record.intervention_id}")
        staged_card = self._trusted_grounding_cards.get(table_id)
        if consume_grounding_card:
            if record.grounding_card is None or staged_card is None:
                raise ValueError("grounding card is no longer staged")
            if staged_card != record.grounding_card:
                raise ValueError("grounding card changed before intervention commit")
        snapshot = TableState.model_validate(state.model_dump())
        self._states[table_id].append(snapshot)
        self._interventions[table_id].append(record.model_copy(deep=True))
        if consume_grounding_card:
            self._trusted_grounding_cards.pop(table_id, None)
        return snapshot.model_copy(deep=True)

    @_synchronized
    def append_intervention_record(self, table_id: str, record: InterventionRecord) -> None:
        """Persist one explainable non-SILENCE action without changing table state."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if latest.conversation.soft_expired:
            raise ValueError("table is soft-expired")
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
        if latest.conversation.soft_expired:
            raise ValueError("table is soft-expired")
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
    def lineage(
        self,
        table_id: str,
        *,
        max_depth: int = MAX_TABLE_LINEAGE_DEPTH,
    ) -> list[TableState]:
        """Return the bounded public table chain from oldest ancestor to current."""
        if max_depth < 1:
            raise ValueError("lineage max_depth must be positive")
        seen: set[str] = set()
        snapshots: list[TableState] = []
        current_id: str | None = table_id
        while current_id is not None:
            if current_id in seen:
                raise ValueError("table lineage contains a cycle")
            if len(snapshots) >= max_depth:
                raise ValueError("table lineage exceeds the maximum depth")
            seen.add(current_id)
            try:
                current = self.get(current_id)
            except KeyError as error:
                raise ValueError(f"unknown lineage table: {current_id}") from error
            snapshots.append(current)
            current_id = current.origin_table_id
        snapshots.reverse()
        return snapshots

    @_synchronized
    def turns(self, table_id: str) -> list[HumanTurn]:
        self.get(table_id)
        return [turn.model_copy(deep=True) for turn in self._turns[table_id]]

    @_synchronized
    def stage_summaries(self, table_id: str) -> list[StageSummary]:
        """Return immutable summary revisions; the latest published row is last."""
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._stage_summaries[table_id]]

    @_synchronized
    def latest_stage_summary(self, table_id: str) -> StageSummary | None:
        self.get(table_id)
        rows = self._stage_summaries[table_id]
        latest = next((item for item in reversed(rows) if item.status == "published"), None)
        return latest.model_copy(deep=True) if latest is not None else None

    @_synchronized
    def append_stage_summary_bundle(
        self,
        table_id: str,
        state: TableState,
        summary: StageSummary,
    ) -> TableState:
        """Atomically publish one summary revision and advance its state reference."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if latest.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("summary state must be the next snapshot for its table")
        if summary.table_id != table_id:
            raise ValueError("summary must belong to the table")
        if summary.input_state_version != latest.version:
            raise ValueError("summary input version is stale")
        if summary.published_state_version != state.version:
            raise ValueError("summary publication version must match state")
        if state.latest_stage_summary_id != summary.summary_id:
            raise ValueError("state must reference the published summary")
        existing = [item for item in self._stage_summaries[table_id] if item.summary_id == summary.summary_id]
        expected_revision = (max((item.revision for item in existing), default=0) + 1)
        if summary.revision != expected_revision:
            raise ValueError("summary revision must advance exactly once")
        if summary.status != "published":
            raise ValueError("new summary revisions must be published")
        turn_ids = {turn.turn_id for turn in self._turns[table_id]}
        evidence_items = [
            *summary.clarified,
            *summary.disagreements,
            *summary.missing,
            *([summary.next_focus] if summary.next_focus is not None else []),
        ]
        total_chars = sum(len(item.text) for item in evidence_items)
        if total_chars > 2400:
            raise ValueError("summary text budget exceeded")
        participant_ids = set(latest.participants)
        if any(
            participant_id not in participant_ids
            for item in summary.disagreements
            for participant_id in item.participant_ids
        ):
            raise ValueError("summary attribution references an unknown participant")
        if any(turn_id not in turn_ids for item in evidence_items for turn_id in item.evidence_turns):
            raise ValueError("summary evidence must reference committed turns from this table")
        snapshots = TableState.model_validate(state.model_dump())
        for index, item in enumerate(self._stage_summaries[table_id]):
            if item.summary_id == summary.summary_id and item.status == "published":
                self._stage_summaries[table_id][index] = item.model_copy(update={"status": "superseded"})
        self._states[table_id].append(snapshots)
        self._stage_summaries[table_id].append(summary.model_copy(deep=True))
        return snapshots.model_copy(deep=True)

    @_synchronized
    def append_summary_feedback(
        self, feedback: StageSummaryFeedback
    ) -> tuple[StageSummaryFeedback, bool]:
        """Persist one member correction idempotently against an existing revision."""
        state = self.get(feedback.table_id)
        if feedback.participant_id not in state.participants:
            raise ValueError("summary feedback author must be a table participant")
        if not any(
            item.summary_id == feedback.summary_id and item.revision == feedback.summary_revision
            for item in self._stage_summaries[feedback.table_id]
        ):
            raise KeyError(f"unknown summary revision: {feedback.summary_id}:{feedback.summary_revision}")
        existing = next(
            (item for item in self._summary_feedback[feedback.table_id] if item.feedback_id == feedback.feedback_id),
            None,
        )
        if existing is not None:
            if existing.model_dump(mode="json") != feedback.model_dump(mode="json"):
                raise ValueError("feedback_id already belongs to a different feedback")
            return existing.model_copy(deep=True), False
        self._summary_feedback[feedback.table_id].append(feedback.model_copy(deep=True))
        return feedback.model_copy(deep=True), True

    @_synchronized
    def summary_feedback(self, table_id: str) -> list[StageSummaryFeedback]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._summary_feedback[table_id]]

    @_synchronized
    def apply_summary_feedback_revision(
        self, table_id: str, feedback_id: str
    ) -> tuple[StageSummary, StageSummaryFeedback, TableState]:
        """Apply one correction as a new immutable summary revision."""
        current = self.get(table_id)
        feedback = next(
            (item for item in self._summary_feedback[table_id] if item.feedback_id == feedback_id),
            None,
        )
        if feedback is None:
            raise KeyError(f"unknown summary feedback: {feedback_id}")
        latest = self.latest_stage_summary(table_id)
        if latest is None or latest.summary_id != feedback.summary_id or latest.revision != feedback.summary_revision:
            raise ValueError("feedback must target the latest published summary")
        if feedback.status == "applied":
            return latest, feedback, current
        missing = list(latest.missing)
        if feedback.kind != "ready_to_advance" and (feedback.note or feedback.evidence_turns):
            if len(missing) >= 3:
                missing = missing[:2]
            missing.append({
                "text": feedback.note or "参与者请求重新核对这段总结",
                "evidence_turns": feedback.evidence_turns or [latest.covered_turn_end],
            })
        revised = StageSummary(
            **latest.model_dump(exclude={"revision", "status", "input_state_version", "published_state_version", "created_at", "missing", "used_fallback"}),
            revision=latest.revision + 1,
            status="published",
            input_state_version=current.version,
            published_state_version=current.version + 1,
            missing=missing,
            created_at=time.time(),
            used_fallback=True,
        )
        next_state = current.model_copy(update={
            "version": current.version + 1,
            "latest_stage_summary_id": revised.summary_id,
            "latest_stage_summary_revision": revised.revision,
        })
        committed = self.append_stage_summary_bundle(table_id, next_state, revised)
        index = self._summary_feedback[table_id].index(feedback)
        applied = feedback.model_copy(update={"status": "applied"})
        self._summary_feedback[table_id][index] = applied
        return revised.model_copy(deep=True), applied.model_copy(deep=True), committed

    @_synchronized
    def append_agent_run(self, record: AgentRunRecord) -> tuple[AgentRunRecord, bool]:
        """Persist redacted run metadata only; raw prompts and completions never enter the ledger."""
        state = self.get(record.table_id)
        if record.trigger_turn_id not in {turn.turn_id for turn in self._turns[record.table_id]}:
            raise ValueError("agent run trigger_turn_id must reference a committed turn")
        existing = next(
            (item for item in self._agent_runs[record.table_id] if item.run_id == record.run_id),
            None,
        )
        if existing is not None:
            if existing.model_dump(mode="json") != record.model_dump(mode="json"):
                raise ValueError("run_id already belongs to a different run")
            return existing.model_copy(deep=True), False
        self._agent_runs[record.table_id].append(record.model_copy(deep=True))
        return record.model_copy(deep=True), True

    @_synchronized
    def agent_runs(self, table_id: str) -> list[AgentRunRecord]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._agent_runs[table_id]]

    @_synchronized
    def set_trusted_grounding_card(self, table_id: str, card: GroundingCard) -> None:
        """Stage one validated demo-injected source for the table's next GROUND action."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
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
    def peek_trusted_grounding_card(self, table_id: str) -> GroundingCard | None:
        """Read the staged source without consuming it before a bundle commit."""
        self.get(table_id)
        card = self._trusted_grounding_cards.get(table_id)
        return card.model_copy(deep=True) if card is not None else None

    @_synchronized
    def _append(self, table_id: str, state: TableState) -> TableState:
        snapshot = TableState.model_validate(state.model_dump())
        self._states[table_id].append(snapshot)
        return snapshot.model_copy(deep=True)


class JsonTableRepository(InMemoryTableRepository):
    """Atomically-written JSON snapshots with optional cross-process locking.

    The JSON file remains intentionally simple for the competition deployment,
    but every top-level operation now takes a sibling lock file and refreshes
    from disk first.  Two ASGI workers sharing the same path therefore cannot
    interleave a read/modify/write transaction or silently overwrite a newer
    snapshot.  A database/event bus can still be substituted through the same
    repository protocol when deployment scale requires it.
    """

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.path = Path(path)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        if self.path.exists():
            self._replace_loaded(self._load())

    def _replace_loaded(self, loaded: tuple[Any, ...]) -> None:
        (
            self._states,
            self._turns,
            self._trusted_grounding_cards,
            self._interventions,
            self._invitations,
            self._join_requests,
            self._follow_up_outcomes,
            self._value_feedback,
            self._comments,
            self._comment_promotions,
            self._no_match,
            self._account_invitation_preferences,
            self._safety_reports,
            self._safety_report_audits,
            self._safety_resolutions,
            self._safety_strikes,
            self._personal_context_consents,
            self._behavior_events,
            self._saved_tables,
            self._public_source_signals,
            self._stage_summaries,
            self._summary_feedback,
            self._agent_runs,
        ) = loaded

    @contextmanager
    def _external_lock(self):
        """Take a small sibling lock that works on Windows and POSIX hosts."""

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _before_operation(self) -> None:
        if self.path.exists():
            self._replace_loaded(self._load())

    @_synchronized
    def create(
        self,
        table_id: str,
        core_question: str,
        participants: Sequence[ParticipantSeed],
        *,
        origin_table_id: str | None = None,
        origin_signal_ids: Sequence[str] | None = None,
        origin_signals: Sequence[ContentSignal] | None = None,
        demo: DemoSession | None = None,
    ) -> TableState:
        if table_id in self._states:
            raise ValueError(f"table already exists: {table_id}")
        if len(participants) > MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
        origin_ids = list(
            origin_signal_ids
            or [signal.signal_id for signal in (origin_signals or [])]
        )
        public_signals = _index_public_source_signals(origin_signals, origin_ids)
        participants = [
            self.apply_account_invitation_preference(seed)
            for seed in participants
        ]
        state = build_initial_state(
            table_id,
            core_question,
            participants,
            origin_table_id,
            origin_ids,
        )
        if demo is not None:
            if set(state.participants) != {demo.owner_participant_id, *demo.simulated_participant_ids}:
                raise ValueError("demo participants must match the owner and simulated identities")
            state.demo = demo.model_copy(deep=True)
        states = {**self._states, table_id: [state]}
        turns = {**self._turns, table_id: []}
        interventions = {**self._interventions, table_id: []}
        invitations = {**self._invitations, table_id: []}
        join_requests = {**self._join_requests, table_id: []}
        outcomes = {**self._follow_up_outcomes, table_id: {}}
        feedback = {**self._value_feedback, table_id: {}}
        comments = {**self._comments, table_id: []}
        comment_promotions = {**self._comment_promotions, table_id: []}
        reports = {**self._safety_reports, table_id: []}
        report_audits = {**self._safety_report_audits, table_id: []}
        resolutions = {**self._safety_resolutions, table_id: []}
        safety_strikes = {**self._safety_strikes, table_id: {}}
        public_source_signals = {
            **self._public_source_signals,
            table_id: public_signals,
        }
        stage_summaries = {**self._stage_summaries, table_id: []}
        summary_feedback = {**self._summary_feedback, table_id: []}
        agent_runs = {**self._agent_runs, table_id: []}
        self._commit(
            states, turns, self._trusted_grounding_cards, interventions, invitations,
            outcomes, feedback, comments, self._no_match, reports,
            comment_promotions=comment_promotions,
            safety_report_audits=report_audits,
            safety_resolutions=resolutions,
            safety_strikes=safety_strikes,
            public_source_signals=public_source_signals,
            join_requests=join_requests,
            stage_summaries=stage_summaries,
            summary_feedback=summary_feedback,
            agent_runs=agent_runs,
        )
        return state.model_copy(deep=True)

    @_synchronized
    def create_join_request(self, request: JoinRequest) -> tuple[JoinRequest, bool]:
        saved, created = super().create_join_request(request)
        if created:
            self._commit(self._states, self._turns, join_requests=self._join_requests)
        return saved, created

    @_synchronized
    def approve_join_request(
        self, table_id: str, request_id: str, inviter_id: str, reason: str
    ) -> tuple[JoinRequest, Invitation]:
        saved, invitation = super().approve_join_request(
            table_id, request_id, inviter_id, reason
        )
        self._commit(self._states, self._turns, join_requests=self._join_requests)
        return saved, invitation

    @_synchronized
    def decline_join_request(
        self, table_id: str, request_id: str, member_id: str
    ) -> JoinRequest:
        saved = super().decline_join_request(table_id, request_id, member_id)
        self._commit(self._states, self._turns, join_requests=self._join_requests)
        return saved

    @_synchronized
    def record_safety_report(self, report: SafetyReport) -> tuple[SafetyReport, bool]:
        state = self.get(report.table_id)
        if report.state_version != state.version:
            raise ValueError("safety report must reference the current table state")
        if report.reporter_id not in state.participants:
            raise ValueError("reporter must be a table participant")
        if report.target_participant_id not in state.participants:
            raise ValueError("target must be a table participant")
        existing = next(
            (item for item in self._safety_reports[report.table_id] if item.report_id == report.report_id),
            None,
        )
        if existing is not None:
            if existing.model_dump(mode="json") != report.model_dump(mode="json"):
                raise ValueError("report_id already belongs to a different report")
            return existing.model_copy(deep=True), False
        reports = {
            **self._safety_reports,
            report.table_id: [*self._safety_reports[report.table_id], report.model_copy(deep=True)],
        }
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards,
            self._interventions, self._invitations, self._follow_up_outcomes,
            self._value_feedback, self._comments, self._no_match, reports,
        )
        return report.model_copy(deep=True), True

    @_synchronized
    def update_safety_report_status(
        self,
        table_id: str,
        report_id: str,
        status: str,
        *,
        moderator_id: str = "system",
        reason: str | None = None,
    ) -> SafetyReport:
        """Advance and atomically persist one private report status."""
        self.get(table_id)
        if status not in {"acknowledged", "resolved"}:
            raise ValueError("unsupported safety report status")
        if not moderator_id.strip():
            raise ValueError("moderator_id must be non-empty")
        for index, report in enumerate(self._safety_reports[table_id]):
            if report.report_id != report_id:
                continue
            if report.status == status:
                return report.model_copy(deep=True)
            allowed = {
                "open": {"acknowledged", "resolved"},
                "acknowledged": {"resolved"},
                "resolved": set(),
            }
            if status not in allowed[report.status]:
                raise ValueError("safety report status cannot move backwards")
            updated = report.model_copy(update={"status": status})
            audit = SafetyReportStatusAudit(
                event_id=f"{table_id}:{report_id}:{status}",
                table_id=table_id,
                report_id=report_id,
                moderator_id=moderator_id.strip(),
                from_status=report.status,
                to_status=status,
                reason=reason.strip() if reason is not None and reason.strip() else None,
            )
            reports = {
                **self._safety_reports,
                table_id: [
                    updated.model_copy(deep=True) if item.report_id == report_id else item
                    for item in self._safety_reports[table_id]
                ],
            }
            report_audits = {
                **self._safety_report_audits,
                table_id: [*self._safety_report_audits[table_id], audit],
            }
            self._commit(
                self._states, self._turns, self._trusted_grounding_cards,
                self._interventions, self._invitations, self._follow_up_outcomes,
                self._value_feedback, self._comments, self._no_match, reports,
                safety_report_audits=report_audits,
            )
            return updated.model_copy(deep=True)
        raise KeyError(f"unknown safety report: {report_id}")

    @_synchronized
    def resolve_safety(
        self,
        table_id: str,
        action: str,
        moderator_id: str,
        reason: str,
        participant_id: str | None = None,
    ) -> tuple[TableState, SafetyResolution]:
        """Persist the safety state and moderator audit in one JSON commit."""
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if state.conversation.safety_level is not SafetyLevel.CRITICAL:
            raise ValueError("table is not paused for safety review")
        if action not in {"resume", "remove_participant"}:
            raise ValueError("unsupported safety resolution action")
        if not moderator_id.strip() or not reason.strip():
            raise ValueError("moderator_id and reason must be non-empty")
        if action == "resume" and participant_id is not None:
            raise ValueError("resume must not include participant_id")
        if action == "remove_participant":
            if not participant_id or participant_id not in state.participants:
                raise ValueError("participant_id must be a current table participant")
        updated = state.model_copy(deep=True)
        updated.version += 1
        if action == "remove_participant":
            del updated.participants[participant_id]  # type: ignore[index]
        updated.conversation.safety_level = SafetyLevel.NORMAL
        updated.conversation.state = (
            "sync_active" if updated.conversation.mode is ConversationMode.SYNC else "active"
        )
        updated.intervention.recommended_action = Action.SILENCE
        updated.agent.status = "active"
        snapshot = TableState.model_validate(updated.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        resolution = SafetyResolution(
            resolution_id=f"{table_id}:safety-resolution:{snapshot.version}",
            table_id=table_id,
            action=action,
            moderator_id=moderator_id.strip(),
            participant_id=participant_id,
            reason=reason.strip(),
            from_state_version=state.version,
            state_version=snapshot.version,
        )
        resolutions = {
            **self._safety_resolutions,
            table_id: [*self._safety_resolutions[table_id], resolution.model_copy(deep=True)],
        }
        self._commit(
            states, self._turns, self._trusted_grounding_cards, self._interventions,
            self._invitations, self._follow_up_outcomes, self._value_feedback,
            self._comments, self._no_match, self._safety_reports,
            self._personal_context_consents,
            safety_resolutions=resolutions,
        )
        return snapshot.model_copy(deep=True), resolution.model_copy(deep=True)

    @_synchronized
    def record_safety_strike(self, table_id: str, participant_id: str) -> int:
        """Persist a bounded private boundary-violation count for one actor."""
        self.get(table_id)
        if not participant_id.strip():
            raise ValueError("safety strike actor must be non-empty")
        current = self._safety_strikes.get(table_id, {}).get(participant_id, 0)
        if current >= MAX_SAFETY_STRIKES_PER_PARTICIPANT:
            return current
        if participant_id not in self._safety_strikes.get(table_id, {}) and len(self._safety_strikes.get(table_id, {})) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError("safety strike ledger is full")
        counts = {
            **self._safety_strikes,
            table_id: {
                **self._safety_strikes.get(table_id, {}),
                participant_id: current + 1,
            },
        }
        self._commit(self._states, self._turns, safety_strikes=counts)
        return current + 1

    @_synchronized
    def set_personal_context_consent(
        self, consent: PersonalContextConsent
    ) -> PersonalContextConsent:
        consents = {
            **self._personal_context_consents,
            consent.viewer_id: consent.model_copy(deep=True),
        }
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards,
            self._interventions, self._invitations, self._follow_up_outcomes,
            self._value_feedback, self._comments, self._no_match,
            self._safety_reports, consents,
        )
        return consent.model_copy(deep=True)

    @_synchronized
    def revoke_personal_context_consent(self, viewer_id: str) -> bool:
        if not viewer_id.strip():
            raise ValueError("viewer_id must be non-empty")
        if viewer_id not in self._personal_context_consents:
            return False
        consents = dict(self._personal_context_consents)
        consents.pop(viewer_id)
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards,
            self._interventions, self._invitations, self._follow_up_outcomes,
            self._value_feedback, self._comments, self._no_match,
            self._safety_reports, consents,
        )
        return True

    @_synchronized
    def set_account_invitation_preference(
        self, participant_id: str, preference: InvitationPreference
    ) -> InvitationPreference:
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        rows = {
            **self._account_invitation_preferences,
            participant_id: preference,
        }
        self._commit(
            self._states,
            self._turns,
            account_invitation_preferences=rows,
        )
        return preference

    @_synchronized
    def save_table(self, participant_id: str, table_id: str) -> bool:
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        self.get(table_id)
        existing = self._saved_tables.get(participant_id, [])
        if table_id in existing:
            return False
        if len(existing) >= MAX_SAVED_TABLES_PER_PARTICIPANT:
            raise ValueError(
                f"saved tables cannot exceed {MAX_SAVED_TABLES_PER_PARTICIPANT}"
            )
        rows = {
            **self._saved_tables,
            participant_id: [*existing, table_id],
        }
        self._commit(self._states, self._turns, saved_tables=rows)
        return True

    @_synchronized
    def unsave_table(self, participant_id: str, table_id: str) -> bool:
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        self.get(table_id)
        existing = self._saved_tables.get(participant_id, [])
        if table_id not in existing:
            return False
        remaining = [item for item in existing if item != table_id]
        rows = {**self._saved_tables}
        if remaining:
            rows[participant_id] = remaining
        else:
            rows.pop(participant_id)
        self._commit(self._states, self._turns, saved_tables=rows)
        return True

    @_synchronized
    def set_no_match(self, participant_id: str, blocked_participant_id: str) -> NoMatchPreference:
        preference = NoMatchPreference(
            participant_id=participant_id,
            blocked_participant_id=blocked_participant_id,
        )
        rows = {owner: set(targets) for owner, targets in self._no_match.items()}
        rows.setdefault(participant_id, set()).add(blocked_participant_id)
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards,
            self._interventions, self._invitations, self._follow_up_outcomes,
            self._value_feedback, self._comments, rows,
        )
        return preference

    @_synchronized
    def remove_no_match(self, participant_id: str, blocked_participant_id: str) -> bool:
        if not participant_id.strip() or not blocked_participant_id.strip():
            raise ValueError("participant ids must be non-empty")
        if blocked_participant_id not in self._no_match.get(participant_id, set()):
            return False
        rows = {owner: set(targets) for owner, targets in self._no_match.items()}
        rows[participant_id].remove(blocked_participant_id)
        if not rows[participant_id]:
            rows.pop(participant_id)
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards,
            self._interventions, self._invitations, self._follow_up_outcomes,
            self._value_feedback, self._comments, rows,
        )
        return True

    @_synchronized
    def append_turn(self, table_id: str, turn: HumanTurn) -> TableState:
        committed = turn.model_copy(deep=True)
        current = self.get(table_id)
        if current.conversation.closed:
            raise ValueError("table is closed")
        if current.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        state = observe_turn(current, committed)
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        turns = {**self._turns, table_id: [*self._turns[table_id], committed]}
        event = BehaviorEvent(
            event_id=f"{table_id}:human:{committed.message_id or committed.turn_id}",
            participant_id=committed.participant_id,
            event_type="human_message",
            table_id=table_id,
            state_version=snapshot.version,
        )
        behavior_events = {
            **self._behavior_events,
            committed.participant_id: [*self._behavior_events.get(committed.participant_id, []), event],
        }
        self._commit(
            states, turns, self._trusted_grounding_cards, self._interventions,
            behavior_events=behavior_events,
        )
        return snapshot.model_copy(deep=True)

    @_synchronized
    def append_message_once(
        self, table_id: str, participant_id: str, text: str, message_id: str,
        *, source: str = "human", generation: SimulationGeneration | None = None,
        expected_state_version: int | None = None,
    ) -> tuple[TableState, bool]:
        """Atomically commit one client message and persist the idempotency key."""
        current = self.get(table_id)
        _validate_message_source(current, participant_id, source, expected_state_version)
        if current.conversation.closed:
            raise ValueError("table is closed")
        if current.conversation.soft_expired:
            raise ValueError("table is soft-expired")
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
            source=source,
            generation=generation,
        )
        state = observe_turn(current, turn)
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        turns = {**self._turns, table_id: [*self._turns[table_id], turn]}
        event = BehaviorEvent(
            event_id=f"{table_id}:human:{message_id}",
            participant_id=participant_id,
            event_type="human_message",
            table_id=table_id,
            state_version=snapshot.version,
        )
        behavior_events = {
            **self._behavior_events,
            participant_id: [*self._behavior_events.get(participant_id, []), event],
        }
        self._commit(
            states, turns, self._trusted_grounding_cards, self._interventions,
            behavior_events=behavior_events,
        )
        return snapshot.model_copy(deep=True), True

    @_synchronized
    def soft_expire_table(self, table_id: str, reason: str) -> TableState:
        state = self.get(table_id)
        if not reason.strip():
            raise ValueError("soft-expiry reason must be non-empty")
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            return state
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.conversation.soft_expired = True
        updated.conversation.state = "soft_expired"
        updated.conversation.soft_expiry_reason = reason.strip()
        updated.intervention.recommended_action = Action.SILENCE
        updated.agent.status = "paused"
        snapshot = TableState.model_validate(updated.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        self._commit(states, self._turns, self._trusted_grounding_cards, self._interventions)
        return snapshot.model_copy(deep=True)

    @_synchronized
    def close_table(self, table_id: str) -> TableState:
        """Persist the close migration instead of falling back to in-memory append."""
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
        updated.agent.status = "closed"
        snapshot = TableState.model_validate(updated.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        self._commit(states, self._turns, self._trusted_grounding_cards, self._interventions)
        return snapshot.model_copy(deep=True)

    @_synchronized
    def close_table_for_participant(self, table_id: str, participant_id: str) -> TableState:
        """Atomically persist an actor close snapshot and its private behavior event."""
        state = self.get(table_id)
        if participant_id not in state.participants:
            raise ValueError("close actor must be a table participant")
        if state.conversation.closed:
            self.record_table_closed_behavior(table_id, participant_id)
            return state
        updated = state.model_copy(deep=True)
        updated.version += 1
        updated.phase = Phase.CLOSE
        updated.close_readiness = Level.HIGH
        updated.conversation.state = "closed"
        updated.conversation.closed = True
        updated.intervention.recommended_action = Action.SILENCE
        updated.agent.status = "closed"
        snapshot = TableState.model_validate(updated.model_dump())
        event = _table_closed_behavior_event(table_id, participant_id, snapshot.version)
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        behavior_events = {
            **self._behavior_events,
            participant_id: [*self._behavior_events.get(participant_id, []), event],
        }
        self._commit(
            states,
            self._turns,
            self._trusted_grounding_cards,
            self._interventions,
            self._invitations,
            self._follow_up_outcomes,
            self._value_feedback,
            self._comments,
            self._no_match,
            self._safety_reports,
            self._personal_context_consents,
            behavior_events=behavior_events,
        )
        return snapshot.model_copy(deep=True)

    @_synchronized
    def create_invitation(
        self, table_id: str, inviter_id: str, candidate: ParticipantSeed, reason: str
    ) -> Invitation:
        candidate = self.apply_account_invitation_preference(candidate)
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if inviter_id not in state.participants:
            raise ValueError("inviter must be a table participant")
        if self.is_no_match(inviter_id, candidate.participant_id):
            raise ValueError("participant has disabled matching with this candidate")
        if candidate.participant_id in state.participants:
            raise ValueError("candidate is already a table participant")
        if candidate.roundtable_invite_preference is InvitationPreference.NONE:
            raise ValueError("candidate has disabled roundtable invitations")
        if len(state.participants) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
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
    def record_follow_up_outcome(self, outcome: FollowUpOutcome) -> FollowUpOutcome:
        state = self.get(outcome.table_id)
        if not state.conversation.closed:
            raise ValueError("follow-up outcomes require a closed table")
        if outcome.participant_id not in state.participants:
            raise ValueError(f"unknown participant: {outcome.participant_id}")
        previous = self._follow_up_outcomes[outcome.table_id].get(outcome.follow_up_index)
        outcomes = {**self._follow_up_outcomes, outcome.table_id: {
            **self._follow_up_outcomes[outcome.table_id],
            outcome.follow_up_index: outcome.model_copy(deep=True),
        }}
        behavior_event = _follow_up_behavior_event(outcome, state.version, previous)
        behavior_events = self._behavior_events
        if behavior_event is not None:
            behavior_events = {
                **self._behavior_events,
                outcome.participant_id: [
                    *self._behavior_events.get(outcome.participant_id, []),
                    behavior_event,
                ],
            }
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards,
            self._interventions, self._invitations, outcomes,
            behavior_events=behavior_events,
        )
        return outcome.model_copy(deep=True)

    @_synchronized
    def follow_up_outcomes(self, table_id: str) -> list[FollowUpOutcome]:
        self.get(table_id)
        return [
            self._follow_up_outcomes[table_id][index].model_copy(deep=True)
            for index in sorted(self._follow_up_outcomes[table_id])
        ]

    @_synchronized
    def record_value_feedback(self, feedback: ValueFeedback) -> ValueFeedback:
        state = self.get(feedback.table_id)
        if not state.conversation.closed:
            raise ValueError("value feedback requires a closed table")
        if feedback.state_version != state.version:
            raise ValueError("value feedback must reference the current closed state")
        if feedback.participant_id not in state.participants:
            raise ValueError(f"unknown participant: {feedback.participant_id}")
        behavior_event = _value_feedback_behavior_event(
            feedback.table_id, feedback.participant_id, state.version
        )
        existing_event = next(
            (
                item
                for item in self._behavior_events.get(feedback.participant_id, [])
                if item.event_id == behavior_event.event_id
            ),
            None,
        )
        if existing_event is not None and existing_event.model_dump(mode="json") != behavior_event.model_dump(mode="json"):
            raise ValueError("event_id already belongs to a different behavior event")
        rows = {
            **self._value_feedback,
            feedback.table_id: {
                **self._value_feedback[feedback.table_id],
                feedback.participant_id: feedback.model_copy(deep=True),
            },
        }
        behavior_events = self._behavior_events
        if existing_event is None:
            behavior_events = {
                **self._behavior_events,
                feedback.participant_id: [
                    *self._behavior_events.get(feedback.participant_id, []),
                    behavior_event,
                ],
            }
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards,
            self._interventions, self._invitations, self._follow_up_outcomes, rows,
            behavior_events=behavior_events,
        )
        return feedback.model_copy(deep=True)

    @_synchronized
    def value_feedback(self, table_id: str) -> list[ValueFeedback]:
        self.get(table_id)
        return [
            self._value_feedback[table_id][participant_id].model_copy(deep=True)
            for participant_id in sorted(self._value_feedback[table_id])
        ]

    @_synchronized
    def append_comment_once(self, comment: PeripheralComment) -> tuple[PeripheralComment, bool]:
        state = self.get(comment.table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if comment.state_version != state.version:
            raise ValueError("comment must reference the current table state")
        existing = next(
            (item for item in self._comments[comment.table_id] if item.comment_id == comment.comment_id),
            None,
        )
        if existing is not None:
            if existing.author_id != comment.author_id or existing.text != comment.text:
                raise ValueError("comment_id already belongs to different comment")
            return existing.model_copy(deep=True), False
        rows = {
            **self._comments,
            comment.table_id: [*self._comments[comment.table_id], comment.model_copy(deep=True)],
        }
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards,
            self._interventions, self._invitations, self._follow_up_outcomes,
            self._value_feedback, rows,
        )
        return comment.model_copy(deep=True), True

    @_synchronized
    def comments(self, table_id: str) -> list[PeripheralComment]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._comments[table_id]]

    @_synchronized
    def promote_comment_once(
        self,
        table_id: str,
        comment_id: str,
        promoter_id: str,
        *,
        expected_state_version: int | None = None,
    ) -> tuple[CommentPromotion, TableState, bool]:
        current = self.get(table_id)
        if current.conversation.closed:
            raise ValueError("table is closed")
        if current.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        existing = next(
            (item for item in self._comment_promotions[table_id] if item.comment_id == comment_id),
            None,
        )
        if existing is not None:
            if existing.promoter_id != promoter_id:
                raise ValueError("comment_id is already promoted by another participant")
            return existing.model_copy(deep=True), current, False
        if promoter_id not in current.participants:
            raise PermissionError("promoter must be a table participant")
        if expected_state_version is not None and current.version != expected_state_version:
            raise ValueError("table changed; retry comment promotion")
        comment = next(
            (item for item in self._comments[table_id] if item.comment_id == comment_id),
            None,
        )
        if comment is None:
            raise KeyError(f"unknown comment: {comment_id}")
        turn_id = max((item.turn_id for item in self._turns[table_id]), default=0) + 1
        message_id = f"{table_id}:comment:{comment_id}"
        turn = HumanTurn(
            turn_id=turn_id,
            participant_id=promoter_id,
            text=comment.text,
            message_id=message_id,
            source_comment_id=comment.comment_id,
        )
        state = observe_turn(current, turn)
        promotion = CommentPromotion(
            promotion_id=f"{table_id}:comment-promotion:{comment_id}",
            table_id=table_id,
            comment_id=comment.comment_id,
            promoter_id=promoter_id,
            turn_id=turn.turn_id,
            state_version=state.version,
            message_id=message_id,
        )
        states = {**self._states, table_id: [*self._states[table_id], TableState.model_validate(state.model_dump())]}
        turns = {**self._turns, table_id: [*self._turns[table_id], turn]}
        promotions = {
            **self._comment_promotions,
            table_id: [*self._comment_promotions[table_id], promotion.model_copy(deep=True)],
        }
        behavior_event = BehaviorEvent(
            event_id=f"{table_id}:human:{message_id}",
            participant_id=promoter_id,
            event_type="human_message",
            table_id=table_id,
            state_version=state.version,
        )
        behavior_events = {
            **self._behavior_events,
            promoter_id: [*self._behavior_events.get(promoter_id, []), behavior_event],
        }
        self._commit(
            states, turns, self._trusted_grounding_cards, self._interventions,
            self._invitations, self._follow_up_outcomes, self._value_feedback,
            self._comments, self._no_match, self._safety_reports,
            self._personal_context_consents, comment_promotions=promotions,
            behavior_events=behavior_events,
        )
        return promotion.model_copy(deep=True), states[table_id][-1].model_copy(deep=True), True

    @_synchronized
    def comment_promotions(self, table_id: str) -> list[CommentPromotion]:
        self.get(table_id)
        return [item.model_copy(deep=True) for item in self._comment_promotions[table_id]]

    @_synchronized
    def record_behavior_event(self, event: BehaviorEvent) -> tuple[BehaviorEvent, bool]:
        if event.event_type in {"table_closed", "value_feedback_submitted"}:
            raise ValueError("server-generated behavior events require a dedicated repository path")
        return self._record_behavior_event(event)

    def _record_behavior_event(self, event: BehaviorEvent) -> tuple[BehaviorEvent, bool]:
        state = self.get(event.table_id)
        _validate_behavior_event_context(state, event)
        if event.state_version is not None and event.state_version > state.version:
            raise ValueError("behavior event cannot reference a future state version")
        existing = next(
            (item for item in self._behavior_events.get(event.participant_id, []) if item.event_id == event.event_id),
            None,
        )
        if existing is not None:
            if existing.model_dump(mode="json") != event.model_dump(mode="json"):
                raise ValueError("event_id already belongs to a different behavior event")
            return existing.model_copy(deep=True), False
        rows = {
            **self._behavior_events,
            event.participant_id: [*self._behavior_events.get(event.participant_id, []), event.model_copy(deep=True)],
        }
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards, self._interventions,
            self._invitations, self._follow_up_outcomes, self._value_feedback,
            self._comments, self._no_match, self._safety_reports,
            self._personal_context_consents, behavior_events=rows,
        )
        return event.model_copy(deep=True), True

    @_synchronized
    def clear_behavior_events(self, participant_id: str) -> bool:
        """Atomically clear one participant's private behavior ledger."""
        if not participant_id.strip():
            raise ValueError("participant_id must be non-empty")
        if participant_id not in self._behavior_events:
            return False
        behavior_events = {**self._behavior_events}
        behavior_events.pop(participant_id)
        self._commit(
            self._states, self._turns, self._trusted_grounding_cards, self._interventions,
            self._invitations, self._follow_up_outcomes, self._value_feedback,
            self._comments, self._no_match, self._safety_reports,
            self._personal_context_consents, behavior_events=behavior_events,
        )
        return True

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
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if accept and any(
            self.is_no_match(member_id, participant_id)
            for member_id in state.participants
        ):
            raise ValueError("participant has disabled matching with this table")
        if accept and len(state.participants) >= MAX_TABLE_PARTICIPANTS:
            raise ValueError(f"table cannot exceed {MAX_TABLE_PARTICIPANTS} participants")
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
            roundtable_invite_preference=seed.roundtable_invite_preference,
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
        if latest.conversation.soft_expired:
            raise ValueError("table is soft-expired")
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
        state = self.get(table_id)
        if state.conversation.closed:
            raise ValueError("table is closed")
        if state.conversation.soft_expired:
            raise ValueError("table is soft-expired")
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
    def peek_trusted_grounding_card(self, table_id: str) -> GroundingCard | None:
        """Read a staged source without persisting a removal."""
        self.get(table_id)
        card = self._trusted_grounding_cards.get(table_id)
        return card.model_copy(deep=True) if card is not None else None

    @_synchronized
    def _append(self, table_id: str, state: TableState) -> TableState:
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        self._commit(states, self._turns, self._trusted_grounding_cards)
        return snapshot.model_copy(deep=True)

    @_synchronized
    def append_stage_summary_bundle(
        self, table_id: str, state: TableState, summary: StageSummary
    ) -> TableState:
        committed = InMemoryTableRepository.append_stage_summary_bundle(self, table_id, state, summary)
        self._commit(self._states, self._turns)
        return committed

    @_synchronized
    def append_summary_feedback(
        self, feedback: StageSummaryFeedback
    ) -> tuple[StageSummaryFeedback, bool]:
        saved, created = InMemoryTableRepository.append_summary_feedback(self, feedback)
        if created:
            self._commit(self._states, self._turns)
        return saved, created

    @_synchronized
    def append_agent_run(self, record: AgentRunRecord) -> tuple[AgentRunRecord, bool]:
        saved, created = InMemoryTableRepository.append_agent_run(self, record)
        if created:
            self._commit(self._states, self._turns)
        return saved, created

    @_synchronized
    def apply_summary_feedback_revision(
        self, table_id: str, feedback_id: str
    ) -> tuple[StageSummary, StageSummaryFeedback, TableState]:
        result = InMemoryTableRepository.apply_summary_feedback_revision(self, table_id, feedback_id)
        self._commit(self._states, self._turns)
        return result

    @_synchronized
    def append_intervention_bundle(
        self,
        table_id: str,
        state: TableState,
        record: InterventionRecord,
        *,
        consume_grounding_card: bool = False,
    ) -> TableState:
        """Persist state, audit record, and optional card consumption in one JSON snapshot."""
        latest = self.get(table_id)
        if latest.conversation.closed:
            raise ValueError("table is closed")
        if latest.conversation.soft_expired:
            raise ValueError("table is soft-expired")
        if state.table_id != table_id or state.version != latest.version + 1:
            raise ValueError("intervention state must be the next snapshot for its table")
        if record.table_id != table_id or record.state_version != state.version:
            raise ValueError("intervention record must reference the new table state")
        if record.action is Action.SILENCE:
            raise ValueError("SILENCE interventions are not persisted")
        if any(item.intervention_id == record.intervention_id for item in self._interventions[table_id]):
            raise ValueError(f"intervention already exists: {record.intervention_id}")
        cards = dict(self._trusted_grounding_cards)
        staged_card = cards.get(table_id)
        if consume_grounding_card:
            if record.grounding_card is None or staged_card is None:
                raise ValueError("grounding card is no longer staged")
            if staged_card != record.grounding_card:
                raise ValueError("grounding card changed before intervention commit")
            cards.pop(table_id, None)
        snapshot = TableState.model_validate(state.model_dump())
        states = {**self._states, table_id: [*self._states[table_id], snapshot]}
        interventions = {
            **self._interventions,
            table_id: [*self._interventions[table_id], record.model_copy(deep=True)],
        }
        self._commit(states, self._turns, cards, interventions)
        return snapshot.model_copy(deep=True)

    @_synchronized
    def _commit(
        self,
        states: dict[str, list[TableState]],
        turns: dict[str, list[HumanTurn]],
        trusted_grounding_cards: dict[str, GroundingCard] | None = None,
        interventions: dict[str, list[InterventionRecord]] | None = None,
        invitations: dict[str, list[Invitation]] | None = None,
        follow_up_outcomes: dict[str, dict[int, FollowUpOutcome]] | None = None,
        value_feedback: dict[str, dict[str, ValueFeedback]] | None = None,
        comments: dict[str, list[PeripheralComment]] | None = None,
        no_match: dict[str, set[str]] | None = None,
        safety_reports: dict[str, list[SafetyReport]] | None = None,
        personal_context_consents: dict[str, PersonalContextConsent] | None = None,
        comment_promotions: dict[str, list[CommentPromotion]] | None = None,
        behavior_events: dict[str, list[BehaviorEvent]] | None = None,
        safety_resolutions: dict[str, list[SafetyResolution]] | None = None,
        safety_report_audits: dict[str, list[SafetyReportStatusAudit]] | None = None,
        public_source_signals: dict[str, dict[str, ContentSignal]] | None = None,
        join_requests: dict[str, list[JoinRequest]] | None = None,
        safety_strikes: dict[str, dict[str, int]] | None = None,
        account_invitation_preferences: dict[str, InvitationPreference] | None = None,
        saved_tables: dict[str, list[str]] | None = None,
        stage_summaries: dict[str, list[StageSummary]] | None = None,
        summary_feedback: dict[str, list[StageSummaryFeedback]] | None = None,
        agent_runs: dict[str, list[AgentRunRecord]] | None = None,
    ) -> None:
        cards = trusted_grounding_cards if trusted_grounding_cards is not None else self._trusted_grounding_cards
        audit = interventions if interventions is not None else self._interventions
        invite_rows = invitations if invitations is not None else self._invitations
        outcome_rows = follow_up_outcomes if follow_up_outcomes is not None else self._follow_up_outcomes
        feedback_rows = value_feedback if value_feedback is not None else self._value_feedback
        comment_rows = comments if comments is not None else self._comments
        no_match_rows = no_match if no_match is not None else self._no_match
        report_rows = safety_reports if safety_reports is not None else self._safety_reports
        report_audit_rows = (
            safety_report_audits
            if safety_report_audits is not None
            else self._safety_report_audits
        )
        consent_rows = (
            personal_context_consents
            if personal_context_consents is not None
            else self._personal_context_consents
        )
        promotion_rows = (
            comment_promotions
            if comment_promotions is not None
            else self._comment_promotions
        )
        behavior_rows = (
            behavior_events
            if behavior_events is not None
            else self._behavior_events
        )
        resolution_rows = (
            safety_resolutions
            if safety_resolutions is not None
            else self._safety_resolutions
        )
        strike_rows = (
            safety_strikes
            if safety_strikes is not None
            else self._safety_strikes
        )
        public_source_rows = (
            public_source_signals
            if public_source_signals is not None
            else self._public_source_signals
        )
        join_request_rows = (
            join_requests
            if join_requests is not None
            else self._join_requests
        )
        account_preference_rows = (
            account_invitation_preferences
            if account_invitation_preferences is not None
            else self._account_invitation_preferences
        )
        saved_table_rows = (
            saved_tables
            if saved_tables is not None
            else self._saved_tables
        )
        summary_rows = stage_summaries if stage_summaries is not None else self._stage_summaries
        summary_feedback_rows = summary_feedback if summary_feedback is not None else self._summary_feedback
        agent_run_rows = agent_runs if agent_runs is not None else self._agent_runs
        payload = {
            "tables": {
                table_id: {
                    "states": [state.model_dump(mode="json") for state in snapshots],
                    "turns": [turn.model_dump(mode="json") for turn in turns[table_id]],
                    "interventions": [item.model_dump(mode="json") for item in audit[table_id]],
                    "invitations": [item.model_dump(mode="json") for item in invite_rows[table_id]],
                    "join_requests": [
                        item.model_dump(mode="json")
                        for item in join_request_rows[table_id]
                    ],
                    "follow_up_outcomes": {
                        str(index): item.model_dump(mode="json")
                        for index, item in outcome_rows[table_id].items()
                    },
                    "value_feedback": [
                        item.model_dump(mode="json")
                        for item in feedback_rows[table_id].values()
                    ],
                    "comments": [
                        item.model_dump(mode="json")
                        for item in comment_rows[table_id]
                    ],
                    "comment_promotions": [
                        item.model_dump(mode="json")
                        for item in promotion_rows[table_id]
                    ],
                    "safety_reports": [
                        item.model_dump(mode="json")
                        for item in report_rows[table_id]
                    ],
                    "safety_report_audits": [
                        item.model_dump(mode="json")
                        for item in report_audit_rows[table_id]
                    ],
                    "safety_resolutions": [
                        item.model_dump(mode="json")
                        for item in resolution_rows[table_id]
                    ],
                    "stage_summaries": [
                        item.model_dump(mode="json")
                        for item in summary_rows.get(table_id, [])
                    ],
                    "summary_feedback": [
                        item.model_dump(mode="json")
                        for item in summary_feedback_rows.get(table_id, [])
                    ],
                    "agent_runs": [
                        item.model_dump(mode="json")
                        for item in agent_run_rows.get(table_id, [])
                    ],
                }
                for table_id, snapshots in states.items()
            },
            "trusted_grounding_cards": {
                table_id: card.model_dump(mode="json") for table_id, card in cards.items()
            },
            "safety_strikes": {
                table_id: dict(counts) for table_id, counts in strike_rows.items()
            },
            "no_match": {
                participant_id: sorted(targets)
                for participant_id, targets in no_match_rows.items()
            },
            "invitation_preferences": {
                participant_id: preference.value
                for participant_id, preference in account_preference_rows.items()
            },
            "personal_context_consents": {
                viewer_id: consent.model_dump(mode="json")
                for viewer_id, consent in consent_rows.items()
            },
            "behavior_events": {
                participant_id: [item.model_dump(mode="json") for item in rows]
                for participant_id, rows in behavior_rows.items()
            },
            "saved_tables": {
                participant_id: list(table_ids)
                for participant_id, table_ids in saved_table_rows.items()
            },
            "public_source_signals": {
                table_id: [item.model_dump(mode="json") for item in rows.values()]
                for table_id, rows in public_source_rows.items()
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
        self._join_requests = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in join_request_rows.items()
        }
        self._follow_up_outcomes = {
            table_id: {
                index: item.model_copy(deep=True) for index, item in rows.items()
            }
            for table_id, rows in outcome_rows.items()
        }
        self._value_feedback = {
            table_id: {
                participant_id: item.model_copy(deep=True)
                for participant_id, item in rows.items()
            }
            for table_id, rows in feedback_rows.items()
        }
        self._comments = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in comment_rows.items()
        }
        self._comment_promotions = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in promotion_rows.items()
        }
        self._trusted_grounding_cards = {
            table_id: card.model_copy(deep=True) for table_id, card in cards.items()
        }
        self._no_match = {
            participant_id: set(targets)
            for participant_id, targets in no_match_rows.items()
        }
        self._account_invitation_preferences = dict(account_preference_rows)
        self._safety_reports = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in report_rows.items()
        }
        self._safety_report_audits = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in report_audit_rows.items()
        }
        self._personal_context_consents = {
            viewer_id: consent.model_copy(deep=True)
            for viewer_id, consent in consent_rows.items()
        }
        self._behavior_events = {
            participant_id: [item.model_copy(deep=True) for item in rows]
            for participant_id, rows in behavior_rows.items()
        }
        self._saved_tables = {
            participant_id: list(table_ids)
            for participant_id, table_ids in saved_table_rows.items()
        }
        self._safety_resolutions = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in resolution_rows.items()
        }
        self._safety_strikes = {
            table_id: dict(counts) for table_id, counts in strike_rows.items()
        }
        self._public_source_signals = {
            table_id: {
                signal_id: item.model_copy(deep=True)
                for signal_id, item in rows.items()
            }
            for table_id, rows in public_source_rows.items()
        }
        self._stage_summaries = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in summary_rows.items()
        }
        self._summary_feedback = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in summary_feedback_rows.items()
        }
        self._agent_runs = {
            table_id: [item.model_copy(deep=True) for item in rows]
            for table_id, rows in agent_run_rows.items()
        }

    def _load(self) -> tuple[
        dict[str, list[TableState]],
        dict[str, list[HumanTurn]],
        dict[str, GroundingCard],
        dict[str, list[InterventionRecord]],
        dict[str, list[Invitation]],
        dict[str, list[JoinRequest]],
        dict[str, dict[int, FollowUpOutcome]],
        dict[str, dict[str, ValueFeedback]],
        dict[str, list[PeripheralComment]],
        dict[str, list[CommentPromotion]],
        dict[str, set[str]],
        dict[str, InvitationPreference],
        dict[str, list[SafetyReport]],
        dict[str, list[SafetyReportStatusAudit]],
        dict[str, list[SafetyResolution]],
        dict[str, dict[str, int]],
        dict[str, PersonalContextConsent],
        dict[str, list[BehaviorEvent]],
        dict[str, list[str]],
        dict[str, dict[str, ContentSignal]],
        dict[str, list[StageSummary]],
        dict[str, list[StageSummaryFeedback]],
        dict[str, list[AgentRunRecord]],
    ]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid persistence file: {self.path}") from error
        if (not isinstance(payload, dict) or "tables" not in payload
                or not set(payload).issubset({
                    "tables", "trusted_grounding_cards", "no_match",
                    "invitation_preferences",
                    "personal_context_consents", "behavior_events",
                    "saved_tables",
                    "public_source_signals", "safety_strikes",
                })
                or not isinstance(payload["tables"], dict)):
            raise ValueError("invalid persistence file: expected {'tables': {...}}")
        states: dict[str, list[TableState]] = {}
        turns: dict[str, list[HumanTurn]] = {}
        interventions: dict[str, list[InterventionRecord]] = {}
        invitations: dict[str, list[Invitation]] = {}
        join_requests: dict[str, list[JoinRequest]] = {}
        follow_up_outcomes: dict[str, dict[int, FollowUpOutcome]] = {}
        value_feedback: dict[str, dict[str, ValueFeedback]] = {}
        comments: dict[str, list[PeripheralComment]] = {}
        comment_promotions: dict[str, list[CommentPromotion]] = {}
        safety_reports: dict[str, list[SafetyReport]] = {}
        safety_report_audits: dict[str, list[SafetyReportStatusAudit]] = {}
        safety_resolutions: dict[str, list[SafetyResolution]] = {}
        stage_summaries: dict[str, list[StageSummary]] = {}
        summary_feedback: dict[str, list[StageSummaryFeedback]] = {}
        agent_runs: dict[str, list[AgentRunRecord]] = {}
        for table_id, table in payload["tables"].items():
            table_keys = set(table) if isinstance(table, dict) else set()
            if (not isinstance(table_id, str) or not table_id or not isinstance(table, dict)
                    or not {"states", "turns"}.issubset(table_keys)
                    or not table_keys.issubset(
                        {
                            "states", "turns", "interventions", "invitations", "join_requests",
                            "follow_up_outcomes", "value_feedback", "comments",
                            "comment_promotions", "safety_reports",
                            "safety_report_audits", "safety_resolutions",
                            "stage_summaries", "summary_feedback", "agent_runs",
                        }
                    )):
                raise ValueError(f"invalid persistence file: malformed table {table_id!r}")
            try:
                snapshots = [TableState.model_validate(item) for item in table["states"]]
                messages = [HumanTurn.model_validate(item) for item in table["turns"]]
                audit = [InterventionRecord.model_validate(item) for item in table.get("interventions", [])]
                invites = [Invitation.model_validate(item) for item in table.get("invitations", [])]
                raw_join_requests = table.get("join_requests", [])
                if not isinstance(raw_join_requests, list):
                    raise ValueError("join_requests must be an array")
                requests = [JoinRequest.model_validate(item) for item in raw_join_requests]
                raw_outcomes = table.get("follow_up_outcomes", {})
                if not isinstance(raw_outcomes, dict):
                    raise ValueError("follow_up_outcomes must be an object")
                outcomes = {
                    int(index): FollowUpOutcome.model_validate(item)
                    for index, item in raw_outcomes.items()
                }
                raw_feedback = table.get("value_feedback", [])
                if not isinstance(raw_feedback, list):
                    raise ValueError("value_feedback must be an array")
                feedback = [ValueFeedback.model_validate(item) for item in raw_feedback]
                raw_comments = table.get("comments", [])
                if not isinstance(raw_comments, list):
                    raise ValueError("comments must be an array")
                comment_rows = [PeripheralComment.model_validate(item) for item in raw_comments]
                raw_promotions = table.get("comment_promotions", [])
                if not isinstance(raw_promotions, list):
                    raise ValueError("comment_promotions must be an array")
                promotions = [CommentPromotion.model_validate(item) for item in raw_promotions]
                raw_reports = table.get("safety_reports", [])
                if not isinstance(raw_reports, list):
                    raise ValueError("safety_reports must be an array")
                reports = [SafetyReport.model_validate(item) for item in raw_reports]
                raw_report_audits = table.get("safety_report_audits", [])
                if not isinstance(raw_report_audits, list):
                    raise ValueError("safety_report_audits must be an array")
                report_audits = [
                    SafetyReportStatusAudit.model_validate(item)
                    for item in raw_report_audits
                ]
                raw_resolutions = table.get("safety_resolutions", [])
                if not isinstance(raw_resolutions, list):
                    raise ValueError("safety_resolutions must be an array")
                resolutions = [SafetyResolution.model_validate(item) for item in raw_resolutions]
                raw_summaries = table.get("stage_summaries", [])
                raw_summary_feedback = table.get("summary_feedback", [])
                raw_agent_runs = table.get("agent_runs", [])
                if not isinstance(raw_summaries, list) or not isinstance(raw_summary_feedback, list) or not isinstance(raw_agent_runs, list):
                    raise ValueError("summary ledgers must be arrays")
                summaries = [StageSummary.model_validate(item) for item in raw_summaries]
                summary_feedback_rows = [StageSummaryFeedback.model_validate(item) for item in raw_summary_feedback]
                agent_run_rows = [AgentRunRecord.model_validate(item) for item in raw_agent_runs]
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
            if any(item.table_id != table_id for item in requests):
                raise ValueError(f"invalid persistence file: incompatible join requests for table {table_id!r}")
            request_ids = [item.request_id for item in requests]
            request_candidates = [item.candidate.participant_id for item in requests]
            if (
                len(request_ids) != len(set(request_ids))
                or len(requests) > MAX_JOIN_REQUESTS_PER_TABLE
                or len(request_candidates) != len(set(request_candidates))
            ):
                raise ValueError(f"invalid persistence file: duplicate or excessive join requests for table {table_id!r}")
            invitation_ids = {item.invitation_id for item in invites}
            if any(
                item.status == "invited"
                and (item.invitation_id not in invitation_ids
                     or not any(
                         invitation.invitation_id == item.invitation_id
                         and invitation.candidate.participant_id == item.candidate.participant_id
                         for invitation in invites
                     ))
                for item in requests
            ):
                raise ValueError(f"invalid persistence file: broken join request invitation for table {table_id!r}")
            if any(index < 0 or outcome.follow_up_index != index or outcome.table_id != table_id
                   for index, outcome in outcomes.items()):
                raise ValueError(f"invalid persistence file: incompatible follow-up outcomes for table {table_id!r}")
            if any(outcome.participant_id not in snapshots[-1].participants for outcome in outcomes.values()):
                raise ValueError(f"invalid persistence file: unknown follow-up outcome participant for table {table_id!r}")
            if any(
                item.table_id != table_id
                or item.state_version != snapshots[-1].version
                or item.participant_id not in snapshots[-1].participants
                for item in feedback
            ):
                raise ValueError(f"invalid persistence file: incompatible value feedback for table {table_id!r}")
            feedback_participants = [item.participant_id for item in feedback]
            if len(set(feedback_participants)) != len(feedback_participants):
                raise ValueError(f"invalid persistence file: duplicate value feedback for table {table_id!r}")
            if any(
                item.table_id != table_id
                or item.state_version < 0
                for item in comment_rows
            ):
                raise ValueError(f"invalid persistence file: incompatible comments for table {table_id!r}")
            comment_ids = [item.comment_id for item in comment_rows]
            if len(set(comment_ids)) != len(comment_ids):
                raise ValueError(f"invalid persistence file: duplicate comments for table {table_id!r}")
            promotion_ids = [item.promotion_id for item in promotions]
            promotion_comment_ids = [item.comment_id for item in promotions]
            if (
                len(set(promotion_ids)) != len(promotion_ids)
                or len(set(promotion_comment_ids)) != len(promotion_comment_ids)
                or any(
                    item.table_id != table_id
                    or item.comment_id not in comment_ids
                    or item.state_version <= 0
                    or item.state_version > snapshots[-1].version
                    or item.turn_id not in {turn.turn_id for turn in messages}
                    or not any(item.promoter_id in snapshot.participants for snapshot in snapshots)
                    for item in promotions
                )
            ):
                raise ValueError(f"invalid persistence file: incompatible comment promotions for table {table_id!r}")
            comments_by_id = {item.comment_id: item for item in comment_rows}
            turns_by_id = {item.turn_id: item for item in messages}
            for promotion in promotions:
                promoted_turn = turns_by_id.get(promotion.turn_id)
                source_comment = comments_by_id.get(promotion.comment_id)
                if (
                    promoted_turn is None
                    or source_comment is None
                    or promoted_turn.participant_id != promotion.promoter_id
                    or promoted_turn.message_id != promotion.message_id
                    or promoted_turn.source_comment_id != promotion.comment_id
                    or promoted_turn.text != source_comment.text
                ):
                    raise ValueError(f"invalid persistence file: broken comment promotion provenance for table {table_id!r}")
            if any(
                report.table_id != table_id
                or report.state_version < 0
                or not any(
                    report.reporter_id in snapshot.participants
                    and report.target_participant_id in snapshot.participants
                    for snapshot in snapshots
                )
                for report in reports
            ):
                raise ValueError(f"invalid persistence file: incompatible safety reports for table {table_id!r}")
            report_ids = [report.report_id for report in reports]
            if len(set(report_ids)) != len(report_ids):
                raise ValueError(f"invalid persistence file: duplicate safety reports for table {table_id!r}")
            if any(
                audit.table_id != table_id
                or audit.report_id not in report_ids
                for audit in report_audits
            ):
                raise ValueError(f"invalid persistence file: incompatible safety report audits for table {table_id!r}")
            audit_ids = [audit.event_id for audit in report_audits]
            if len(set(audit_ids)) != len(audit_ids):
                raise ValueError(f"invalid persistence file: duplicate safety report audits for table {table_id!r}")
            for report in reports:
                history = [item for item in report_audits if item.report_id == report.report_id]
                if not history:
                    # D78-era snapshots have a final status but no actor history.
                    continue
                current_status = "open"
                for item in history:
                    if item.from_status != current_status:
                        raise ValueError(
                            f"invalid persistence file: broken safety report audit chain for table {table_id!r}"
                        )
                    current_status = item.to_status
                if current_status != report.status:
                    raise ValueError(
                        f"invalid persistence file: safety report status does not match audit chain for table {table_id!r}"
                    )
            if any(
                resolution.table_id != table_id
                or resolution.from_state_version < 0
                or resolution.state_version <= resolution.from_state_version
                or resolution.state_version > snapshots[-1].version
                for resolution in resolutions
            ):
                raise ValueError(f"invalid persistence file: incompatible safety resolutions for table {table_id!r}")
            if any(item.table_id != table_id for item in summaries):
                raise ValueError(f"invalid persistence file: incompatible stage summaries for table {table_id!r}")
            summary_keys = [(item.summary_id, item.revision) for item in summaries]
            if len(summary_keys) != len(set(summary_keys)):
                raise ValueError(f"invalid persistence file: duplicate stage summaries for table {table_id!r}")
            if any(item.table_id != table_id for item in summary_feedback_rows):
                raise ValueError(f"invalid persistence file: incompatible summary feedback for table {table_id!r}")
            feedback_ids = [item.feedback_id for item in summary_feedback_rows]
            if len(feedback_ids) != len(set(feedback_ids)):
                raise ValueError(f"invalid persistence file: duplicate summary feedback for table {table_id!r}")
            if any(item.table_id != table_id for item in agent_run_rows):
                raise ValueError(f"invalid persistence file: incompatible agent runs for table {table_id!r}")
            run_ids = [item.run_id for item in agent_run_rows]
            if len(run_ids) != len(set(run_ids)):
                raise ValueError(f"invalid persistence file: duplicate agent runs for table {table_id!r}")
            resolution_ids = [resolution.resolution_id for resolution in resolutions]
            if len(set(resolution_ids)) != len(resolution_ids):
                raise ValueError(f"invalid persistence file: duplicate safety resolutions for table {table_id!r}")
            states[table_id] = snapshots
            turns[table_id] = messages
            interventions[table_id] = audit
            invitations[table_id] = invites
            join_requests[table_id] = requests
            follow_up_outcomes[table_id] = outcomes
            value_feedback[table_id] = {
                item.participant_id: item for item in feedback
            }
            comments[table_id] = comment_rows
            comment_promotions[table_id] = promotions
            self_reports = reports
            safety_reports[table_id] = self_reports
            safety_report_audits[table_id] = report_audits
            safety_resolutions[table_id] = resolutions
            stage_summaries[table_id] = summaries
            summary_feedback[table_id] = summary_feedback_rows
            agent_runs[table_id] = agent_run_rows
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
        raw_no_match = payload.get("no_match", {})
        if not isinstance(raw_no_match, dict):
            raise ValueError("invalid persistence file: malformed no_match")
        no_match: dict[str, set[str]] = {}
        for participant_id, targets in raw_no_match.items():
            if (
                not isinstance(participant_id, str)
                or not participant_id
                or not isinstance(targets, list)
                or len(set(targets)) != len(targets)
                or any(
                    not isinstance(target, str)
                    or not target
                    or target == participant_id
                    for target in targets
                )
            ):
                raise ValueError("invalid persistence file: invalid no_match participant")
            no_match[participant_id] = set(targets)
        raw_preferences = payload.get("invitation_preferences", {})
        if not isinstance(raw_preferences, dict):
            raise ValueError("invalid persistence file: malformed invitation_preferences")
        account_invitation_preferences: dict[str, InvitationPreference] = {}
        for participant_id, raw_preference in raw_preferences.items():
            if not isinstance(participant_id, str) or not participant_id:
                raise ValueError("invalid persistence file: invalid invitation preference participant")
            try:
                account_invitation_preferences[participant_id] = InvitationPreference(
                    raw_preference
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "invalid persistence file: invalid invitation preference"
                ) from error
        raw_consents = payload.get("personal_context_consents", {})
        if not isinstance(raw_consents, dict):
            raise ValueError("invalid persistence file: malformed personal_context_consents")
        consents: dict[str, PersonalContextConsent] = {}
        for viewer_id, raw_consent in raw_consents.items():
            if not isinstance(viewer_id, str) or not viewer_id:
                raise ValueError("invalid persistence file: invalid personal context viewer")
            try:
                consent = PersonalContextConsent.model_validate(raw_consent)
            except (TypeError, ValueError) as error:
                raise ValueError("invalid persistence file: invalid personal context consent") from error
            if consent.viewer_id != viewer_id:
                raise ValueError("invalid persistence file: personal context viewer mismatch")
            consents[viewer_id] = consent
        raw_behavior = payload.get("behavior_events", {})
        if not isinstance(raw_behavior, dict):
            raise ValueError("invalid persistence file: malformed behavior_events")
        behavior_events: dict[str, list[BehaviorEvent]] = {}
        for participant_id, raw_events in raw_behavior.items():
            if not isinstance(participant_id, str) or not participant_id or not isinstance(raw_events, list):
                raise ValueError("invalid persistence file: invalid behavior participant")
            try:
                events = [BehaviorEvent.model_validate(item) for item in raw_events]
            except (TypeError, ValueError) as error:
                raise ValueError("invalid persistence file: invalid behavior event") from error
            if any(
                item.participant_id != participant_id
                or item.table_id not in states
                or item.state_version is not None and item.state_version > states[item.table_id][-1].version
                for item in events
            ):
                raise ValueError("invalid persistence file: incompatible behavior event")
            for item in events:
                try:
                    _validate_behavior_event_context(states[item.table_id][-1], item)
                except ValueError as error:
                    raise ValueError("invalid persistence file: incompatible behavior event context") from error
            event_ids = [item.event_id for item in events]
            if len(set(event_ids)) != len(event_ids):
                raise ValueError("invalid persistence file: duplicate behavior event")
            behavior_events[participant_id] = events
        raw_saved_tables = payload.get("saved_tables", {})
        if not isinstance(raw_saved_tables, dict):
            raise ValueError("invalid persistence file: malformed saved_tables")
        saved_tables: dict[str, list[str]] = {}
        for participant_id, raw_table_ids in raw_saved_tables.items():
            if (
                not isinstance(participant_id, str)
                or not participant_id
                or not isinstance(raw_table_ids, list)
                or len(raw_table_ids) > MAX_SAVED_TABLES_PER_PARTICIPANT
                or any(
                    not isinstance(table_id, str)
                    or not table_id
                    or table_id not in states
                    for table_id in raw_table_ids
                )
                or len(raw_table_ids) != len(set(raw_table_ids))
            ):
                raise ValueError("invalid persistence file: invalid saved tables")
            saved_tables[participant_id] = list(raw_table_ids)
        raw_public_sources = payload.get("public_source_signals", {})
        if not isinstance(raw_public_sources, dict):
            raise ValueError("invalid persistence file: malformed public_source_signals")
        public_source_signals: dict[str, dict[str, ContentSignal]] = {}
        for table_id, raw_signals in raw_public_sources.items():
            if table_id not in states or not isinstance(table_id, str) or not table_id:
                raise ValueError("invalid persistence file: public source signal for unknown table")
            if not isinstance(raw_signals, list) or len(raw_signals) > MAX_PUBLIC_SOURCE_SIGNALS:
                raise ValueError(
                    f"invalid persistence file: public source snapshot for table {table_id!r} is malformed"
                )
            try:
                signals = [ContentSignal.model_validate(item) for item in raw_signals]
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"invalid persistence file: invalid public source signal for table {table_id!r}"
                ) from error
            signal_ids = [signal.signal_id for signal in signals]
            if len(signal_ids) != len(set(signal_ids)):
                raise ValueError(
                    f"invalid persistence file: duplicate public source signal for table {table_id!r}"
                )
            allowed_ids = set(states[table_id][-1].origin_signal_ids)
            if any(signal_id not in allowed_ids for signal_id in signal_ids):
                raise ValueError(
                    f"invalid persistence file: public source signal is not an origin signal for table {table_id!r}"
                )
            public_source_signals[table_id] = {
                signal.signal_id: signal for signal in signals
            }
        raw_strikes = payload.get("safety_strikes", {})
        if not isinstance(raw_strikes, dict):
            raise ValueError("invalid persistence file: malformed safety_strikes")
        safety_strikes: dict[str, dict[str, int]] = {}
        for table_id, raw_counts in raw_strikes.items():
            if table_id not in states or not isinstance(table_id, str) or not table_id:
                raise ValueError("invalid persistence file: safety strikes for unknown table")
            if not isinstance(raw_counts, dict) or len(raw_counts) > MAX_TABLE_PARTICIPANTS:
                raise ValueError("invalid persistence file: malformed safety strikes")
            counts: dict[str, int] = {}
            for participant_id, count in raw_counts.items():
                if (
                    not isinstance(participant_id, str)
                    or not participant_id
                    or not isinstance(count, int)
                    or isinstance(count, bool)
                    or not 1 <= count <= MAX_SAFETY_STRIKES_PER_PARTICIPANT
                    or not any(participant_id in snapshot.participants for snapshot in states[table_id])
                ):
                    raise ValueError("invalid persistence file: malformed safety strike entry")
                counts[participant_id] = count
            safety_strikes[table_id] = counts
        return (
            states,
            turns,
            cards,
            interventions,
            invitations,
            join_requests,
            follow_up_outcomes,
            value_feedback,
            comments,
            comment_promotions,
            no_match,
            account_invitation_preferences,
            safety_reports,
            safety_report_audits,
            safety_resolutions,
            safety_strikes,
            consents,
            behavior_events,
            saved_tables,
            public_source_signals,
            stage_summaries,
            summary_feedback,
            agent_runs,
        )
