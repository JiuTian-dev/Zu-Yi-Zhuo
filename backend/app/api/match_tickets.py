"""Short-lived capabilities for confirming an authorized source match."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
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


__all__ = ["SourceMatchTicket", "SourceMatchTicketStore"]
