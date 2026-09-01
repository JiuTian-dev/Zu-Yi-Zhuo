"""Short-lived capabilities for confirming an authorized source match."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from threading import RLock
import secrets
import time

from app.domain import MatchPlan, ParticipantSeed


@dataclass(frozen=True)
class SourceMatchTicket:
    """Server-held source candidates behind one opaque preview capability."""

    core_question: str
    table_size: int
    candidates: tuple[ParticipantSeed, ...]
    plan: MatchPlan
    expires_at: float


@dataclass(frozen=True)
class CandidateInvitationTicket:
    """Server-held candidate seed behind one table-member invitation preview."""

    table_id: str
    inviter_id: str
    candidate: ParticipantSeed
    reason: str
    expires_at: float


class SourceMatchTicketStore:
    """Bounded, single-use in-memory store for source-match handoff tickets.

    The store deliberately keeps the candidate payload server-side. The bearer
    token is the only value the browser needs to carry from preview to confirm.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        max_tickets: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_tickets <= 0:
            raise ValueError("max_tickets must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_tickets = max_tickets
        self._clock = clock
        self._lock = RLock()
        self._tickets: dict[str, SourceMatchTicket] = {}
        self._claimed: set[str] = set()

    def issue(
        self,
        *,
        core_question: str,
        table_size: int,
        candidates: Sequence[ParticipantSeed],
        plan: MatchPlan,
    ) -> str:
        """Store a deep-copied preview and return its opaque bearer token."""
        now = self._clock()
        with self._lock:
            self._prune(now)
            if len(self._tickets) >= self._max_tickets:
                raise ValueError("source match preview capacity exhausted")
            token = secrets.token_urlsafe(32)
            self._tickets[token] = SourceMatchTicket(
                core_question=core_question,
                table_size=table_size,
                candidates=tuple(candidate.model_copy(deep=True) for candidate in candidates),
                plan=plan.model_copy(deep=True),
                expires_at=now + self._ttl_seconds,
            )
            return token

    def claim(self, token: str) -> SourceMatchTicket:
        """Atomically reserve a ticket for confirmation, rejecting reuse."""
        now = self._clock()
        with self._lock:
            self._prune(now)
            ticket = self._tickets.get(token)
            if ticket is None or token in self._claimed:
                raise ValueError("source match preview token is unavailable")
            self._claimed.add(token)
            return SourceMatchTicket(
                core_question=ticket.core_question,
                table_size=ticket.table_size,
                candidates=tuple(candidate.model_copy(deep=True) for candidate in ticket.candidates),
                plan=ticket.plan.model_copy(deep=True),
                expires_at=ticket.expires_at,
            )

    def consume(self, token: str) -> None:
        """Permanently consume a claimed ticket after table creation succeeds."""
        with self._lock:
            self._tickets.pop(token, None)
            self._claimed.discard(token)

    def release(self, token: str) -> None:
        """Release a claim when confirmation fails before a table is created."""
        with self._lock:
            ticket = self._tickets.get(token)
            if ticket is None or ticket.expires_at <= self._clock():
                self._tickets.pop(token, None)
                self._claimed.discard(token)
                return
            self._claimed.discard(token)

    def _prune(self, now: float) -> None:
        expired = [token for token, ticket in self._tickets.items() if ticket.expires_at <= now]
        for token in expired:
            self._tickets.pop(token, None)
            self._claimed.discard(token)


class CandidateInvitationTicketStore:
    """Bounded, single-use in-memory store for dynamic candidate invitations."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        max_tickets: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_tickets <= 0:
            raise ValueError("max_tickets must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_tickets = max_tickets
        self._clock = clock
        self._lock = RLock()
        self._tickets: dict[str, CandidateInvitationTicket] = {}
        self._claimed: set[str] = set()

    def issue(
        self,
        *,
        table_id: str,
        inviter_id: str,
        candidate: ParticipantSeed,
        reason: str,
    ) -> str:
        now = self._clock()
        with self._lock:
            self._prune(now)
            if len(self._tickets) >= self._max_tickets:
                raise ValueError("candidate invitation preview capacity exhausted")
            token = secrets.token_urlsafe(32)
            self._tickets[token] = CandidateInvitationTicket(
                table_id=table_id,
                inviter_id=inviter_id,
                candidate=candidate.model_copy(deep=True),
                reason=reason,
                expires_at=now + self._ttl_seconds,
            )
            return token

    def claim(self, token: str) -> CandidateInvitationTicket:
        now = self._clock()
        with self._lock:
            self._prune(now)
            ticket = self._tickets.get(token)
            if ticket is None or token in self._claimed:
                raise ValueError("candidate invitation preview token is unavailable")
            self._claimed.add(token)
            return CandidateInvitationTicket(
                table_id=ticket.table_id,
                inviter_id=ticket.inviter_id,
                candidate=ticket.candidate.model_copy(deep=True),
                reason=ticket.reason,
                expires_at=ticket.expires_at,
            )

    def consume(self, token: str) -> None:
        with self._lock:
            self._tickets.pop(token, None)
            self._claimed.discard(token)

    def release(self, token: str) -> None:
        with self._lock:
            ticket = self._tickets.get(token)
            if ticket is None or ticket.expires_at <= self._clock():
                self._tickets.pop(token, None)
                self._claimed.discard(token)
                return
            self._claimed.discard(token)

    def _prune(self, now: float) -> None:
        expired = [token for token, ticket in self._tickets.items() if ticket.expires_at <= now]
        for token in expired:
            self._tickets.pop(token, None)
            self._claimed.discard(token)


class _SQLiteTicketStore:
    """Shared SQLite ticket primitives used by both handoff stores."""

    table_name = ""

    def __init__(
        self,
        path: str | Path,
        *,
        ttl_seconds: float = 300.0,
        max_tickets: int = 512,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_tickets <= 0:
            raise ValueError("max_tickets must be positive")
        self.path = Path(path)
        self._ttl_seconds = ttl_seconds
        self._max_tickets = max_tickets
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    token TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    claimed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_expires "
                f"ON {self.table_name}(expires_at)"
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _prune(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute(
            f"DELETE FROM {self.table_name} WHERE expires_at <= ?", (now,)
        )

    def _issue(self, payload: dict, now: float) -> str:
        payload = {**payload, "expires_at": now + self._ttl_seconds}
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._prune(connection, now)
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {self.table_name}"
                ).fetchone()[0]
                if count >= self._max_tickets:
                    raise ValueError("source preview ticket capacity exhausted")
                token = secrets.token_urlsafe(32)
                connection.execute(
                    f"INSERT INTO {self.table_name}(token, payload, expires_at) VALUES (?, ?, ?)",
                    (token, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now + self._ttl_seconds),
                )
                connection.execute("COMMIT")
                return token
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()

    def _claim(self, token: str, now: float) -> dict:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._prune(connection, now)
                row = connection.execute(
                    f"SELECT payload FROM {self.table_name} "
                    "WHERE token = ? AND claimed = 0",
                    (token,),
                ).fetchone()
                if row is None:
                    raise ValueError("source preview token is unavailable")
                connection.execute(
                    f"UPDATE {self.table_name} SET claimed = 1 WHERE token = ?",
                    (token,),
                )
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            try:
                payload = json.loads(row[0])
            except (TypeError, json.JSONDecodeError) as error:
                raise ValueError("source preview token payload is invalid") from error
            if not isinstance(payload, dict):
                raise ValueError("source preview token payload is invalid")
            return payload
        finally:
            connection.close()

    def _delete(self, token: str) -> None:
        connection = self._connect()
        try:
            connection.execute(f"DELETE FROM {self.table_name} WHERE token = ?", (token,))
        finally:
            connection.close()

    def _release(self, token: str, now: float) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    f"DELETE FROM {self.table_name} WHERE expires_at <= ?", (now,)
                )
                connection.execute(
                    f"UPDATE {self.table_name} SET claimed = 0 WHERE token = ?",
                    (token,),
                )
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()


class SQLiteSourceMatchTicketStore(_SQLiteTicketStore):
    """Cross-worker source-match handoff store with atomic single-use claims."""

    table_name = "source_match_tickets"

    def issue(
        self,
        *,
        core_question: str,
        table_size: int,
        candidates: Sequence[ParticipantSeed],
        plan: MatchPlan,
    ) -> str:
        return self._issue({
            "core_question": core_question,
            "table_size": table_size,
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "plan": plan.model_dump(mode="json"),
        }, float(self._clock()))

    def claim(self, token: str) -> SourceMatchTicket:
        payload = self._claim(token, float(self._clock()))
        try:
            return SourceMatchTicket(
                core_question=str(payload["core_question"]),
                table_size=int(payload["table_size"]),
                candidates=tuple(ParticipantSeed.model_validate(item) for item in payload["candidates"]),
                plan=MatchPlan.model_validate(payload["plan"]),
                expires_at=float(payload.get("expires_at", 0.0)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("source preview token payload is invalid") from error

    def consume(self, token: str) -> None:
        self._delete(token)

    def release(self, token: str) -> None:
        self._release(token, float(self._clock()))


class SQLiteCandidateInvitationTicketStore(_SQLiteTicketStore):
    """Cross-worker dynamic invitation handoff store."""

    table_name = "candidate_invitation_tickets"

    def issue(
        self,
        *,
        table_id: str,
        inviter_id: str,
        candidate: ParticipantSeed,
        reason: str,
    ) -> str:
        return self._issue({
            "table_id": table_id,
            "inviter_id": inviter_id,
            "candidate": candidate.model_dump(mode="json"),
            "reason": reason,
        }, float(self._clock()))

    def claim(self, token: str) -> CandidateInvitationTicket:
        payload = self._claim(token, float(self._clock()))
        try:
            return CandidateInvitationTicket(
                table_id=str(payload["table_id"]),
                inviter_id=str(payload["inviter_id"]),
                candidate=ParticipantSeed.model_validate(payload["candidate"]),
                reason=str(payload["reason"]),
                expires_at=float(payload.get("expires_at", 0.0)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("source preview token payload is invalid") from error

    def consume(self, token: str) -> None:
        self._delete(token)

    def release(self, token: str) -> None:
        self._release(token, float(self._clock()))


__all__ = [
    "CandidateInvitationTicket",
    "CandidateInvitationTicketStore",
    "SQLiteCandidateInvitationTicketStore",
    "SourceMatchTicket",
    "SourceMatchTicketStore",
    "SQLiteSourceMatchTicketStore",
]
