"""Bounded, self-scoped short-term memory for active-intent clarification."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
import secrets
import time


MAX_INTENT_SESSION_TURNS = 6
MAX_INTENT_SESSIONS = 256
DEFAULT_INTENT_SESSION_TTL_SECONDS = 900.0


class IntentSessionUnavailable(ValueError):
    """The requested session is missing, expired, or belongs to another user."""


class IntentSessionCapacityExhausted(ValueError):
    """The bounded process-local session store has reached capacity."""


class IntentSessionTurnLimitReached(ValueError):
    """The session already accepted its maximum number of user turns."""


@dataclass(frozen=True)
class ActiveIntentSession:
    session_id: str
    participant_id: str
    messages: tuple[str, ...]
    turn_count: int
    max_turns: int
    limit: int
    expires_at: float


class ActiveIntentSessionStore:
    """Thread-safe ephemeral store; session text never enters durable repositories."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_INTENT_SESSION_TTL_SECONDS,
        max_sessions: int = MAX_INTENT_SESSIONS,
        max_turns: int = MAX_INTENT_SESSION_TURNS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("intent session ttl_seconds must be positive")
        if max_sessions <= 0:
            raise ValueError("intent session max_sessions must be positive")
        if max_turns <= 0 or max_turns > MAX_INTENT_SESSION_TURNS:
            raise ValueError(
                f"intent session max_turns must be between 1 and {MAX_INTENT_SESSION_TURNS}"
            )
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._clock = clock
        self._lock = RLock()
        self._sessions: dict[str, ActiveIntentSession] = {}

    def create(self, *, participant_id: str, message: str, limit: int) -> ActiveIntentSession:
        now = self._clock()
        with self._lock:
            self._prune(now)
            if len(self._sessions) >= self._max_sessions:
                raise IntentSessionCapacityExhausted("active intent session capacity exhausted")
            session_id = secrets.token_urlsafe(24)
            while session_id in self._sessions:
                session_id = secrets.token_urlsafe(24)
            session = ActiveIntentSession(
                session_id=session_id,
                participant_id=participant_id,
                messages=(message.strip(),),
                turn_count=1,
                max_turns=self._max_turns,
                limit=limit,
                expires_at=now + self._ttl_seconds,
            )
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str, participant_id: str) -> ActiveIntentSession:
        now = self._clock()
        with self._lock:
            self._prune(now)
            return self._owned_session(session_id, participant_id)

    def append(
        self,
        session_id: str,
        participant_id: str,
        message: str,
        *,
        replace_context: bool = False,
    ) -> ActiveIntentSession:
        now = self._clock()
        with self._lock:
            self._prune(now)
            session = self._owned_session(session_id, participant_id)
            if session.turn_count >= session.max_turns:
                raise IntentSessionTurnLimitReached("active intent session turn limit reached")
            messages = (message.strip(),) if replace_context else session.messages + (message.strip(),)
            updated = ActiveIntentSession(
                session_id=session.session_id,
                participant_id=session.participant_id,
                messages=messages,
                turn_count=session.turn_count + 1,
                max_turns=session.max_turns,
                limit=session.limit,
                expires_at=now + self._ttl_seconds,
            )
            self._sessions[session_id] = updated
            return updated

    def delete(self, session_id: str, participant_id: str) -> None:
        now = self._clock()
        with self._lock:
            self._prune(now)
            self._owned_session(session_id, participant_id)
            self._sessions.pop(session_id, None)

    def _owned_session(self, session_id: str, participant_id: str) -> ActiveIntentSession:
        session = self._sessions.get(session_id)
        if session is None or session.participant_id != participant_id:
            raise IntentSessionUnavailable("active intent session is unavailable")
        return session

    def _prune(self, now: float) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)


__all__ = [
    "ActiveIntentSession",
    "ActiveIntentSessionStore",
    "DEFAULT_INTENT_SESSION_TTL_SECONDS",
    "IntentSessionCapacityExhausted",
    "IntentSessionTurnLimitReached",
    "IntentSessionUnavailable",
    "MAX_INTENT_SESSIONS",
    "MAX_INTENT_SESSION_TURNS",
]
