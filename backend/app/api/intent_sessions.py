"""Bounded, self-scoped short-term memory for active-intent clarification."""

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
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


class SQLiteActiveIntentSessionStore:
    """Cross-worker ephemeral intent sessions with TTL-enforced ownership."""

    def __init__(
        self,
        path: str | Path,
        *,
        ttl_seconds: float = DEFAULT_INTENT_SESSION_TTL_SECONDS,
        max_sessions: int = MAX_INTENT_SESSIONS,
        max_turns: int = MAX_INTENT_SESSION_TURNS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("intent session ttl_seconds must be positive")
        if max_sessions <= 0:
            raise ValueError("intent session max_sessions must be positive")
        if max_turns <= 0 or max_turns > MAX_INTENT_SESSION_TURNS:
            raise ValueError(
                f"intent session max_turns must be between 1 and {MAX_INTENT_SESSION_TURNS}"
            )
        self.path = Path(path)
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._max_turns = max_turns
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS active_intent_sessions (
                    session_id TEXT PRIMARY KEY,
                    participant_id TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    turn_count INTEGER NOT NULL,
                    max_turns INTEGER NOT NULL,
                    session_limit INTEGER NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_active_intent_sessions_expiry "
                "ON active_intent_sessions(expires_at)"
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _prune(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute(
            "DELETE FROM active_intent_sessions WHERE expires_at <= ?", (now,)
        )

    def _row_to_session(self, row: tuple) -> ActiveIntentSession:
        try:
            messages = json.loads(row[2])
            if not isinstance(messages, list):
                raise ValueError
            return ActiveIntentSession(
                session_id=str(row[0]),
                participant_id=str(row[1]),
                messages=tuple(str(item) for item in messages),
                turn_count=int(row[3]),
                max_turns=int(row[4]),
                limit=int(row[5]),
                expires_at=float(row[6]),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise IntentSessionUnavailable("active intent session is unavailable") from error

    def _select_owned(self, connection: sqlite3.Connection, session_id: str, participant_id: str):
        row = connection.execute(
            "SELECT session_id, participant_id, messages, turn_count, max_turns, "
            "session_limit, expires_at FROM active_intent_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None or row[1] != participant_id:
            raise IntentSessionUnavailable("active intent session is unavailable")
        return row

    def create(self, *, participant_id: str, message: str, limit: int) -> ActiveIntentSession:
        now = float(self._clock())
        session_id = secrets.token_urlsafe(24)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._prune(connection, now)
                count = connection.execute(
                    "SELECT COUNT(*) FROM active_intent_sessions"
                ).fetchone()[0]
                if count >= self._max_sessions:
                    raise IntentSessionCapacityExhausted(
                        "active intent session capacity exhausted"
                    )
                while connection.execute(
                    "SELECT 1 FROM active_intent_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone() is not None:
                    session_id = secrets.token_urlsafe(24)
                expires_at = now + self._ttl_seconds
                connection.execute(
                    "INSERT INTO active_intent_sessions "
                    "(session_id, participant_id, messages, turn_count, max_turns, session_limit, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (session_id, participant_id, json.dumps([message.strip()], ensure_ascii=False),
                     1, self._max_turns, limit, expires_at),
                )
                connection.execute("COMMIT")
                return ActiveIntentSession(
                    session_id=session_id,
                    participant_id=participant_id,
                    messages=(message.strip(),),
                    turn_count=1,
                    max_turns=self._max_turns,
                    limit=limit,
                    expires_at=expires_at,
                )
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()

    def get(self, session_id: str, participant_id: str) -> ActiveIntentSession:
        now = float(self._clock())
        connection = self._connect()
        try:
            self._prune(connection, now)
            row = self._select_owned(connection, session_id, participant_id)
            session = self._row_to_session(row)
            if session.expires_at <= now:
                raise IntentSessionUnavailable("active intent session is unavailable")
            return session
        finally:
            connection.close()

    def append(
        self,
        session_id: str,
        participant_id: str,
        message: str,
        *,
        replace_context: bool = False,
    ) -> ActiveIntentSession:
        now = float(self._clock())
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._prune(connection, now)
                row = self._select_owned(connection, session_id, participant_id)
                session = self._row_to_session(row)
                if session.turn_count >= session.max_turns:
                    raise IntentSessionTurnLimitReached(
                        "active intent session turn limit reached"
                    )
                messages = [message.strip()] if replace_context else [*session.messages, message.strip()]
                expires_at = now + self._ttl_seconds
                connection.execute(
                    "UPDATE active_intent_sessions SET messages = ?, turn_count = ?, expires_at = ? "
                    "WHERE session_id = ? AND participant_id = ?",
                    (json.dumps(messages, ensure_ascii=False), session.turn_count + 1,
                     expires_at, session_id, participant_id),
                )
                connection.execute("COMMIT")
                return ActiveIntentSession(
                    session_id=session.session_id,
                    participant_id=session.participant_id,
                    messages=tuple(messages),
                    turn_count=session.turn_count + 1,
                    max_turns=session.max_turns,
                    limit=session.limit,
                    expires_at=expires_at,
                )
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()

    def delete(self, session_id: str, participant_id: str) -> None:
        now = float(self._clock())
        connection = self._connect()
        try:
            self._prune(connection, now)
            self._select_owned(connection, session_id, participant_id)
            connection.execute(
                "DELETE FROM active_intent_sessions WHERE session_id = ?", (session_id,)
            )
        finally:
            connection.close()


__all__ = [
    "ActiveIntentSession",
    "ActiveIntentSessionStore",
    "SQLiteActiveIntentSessionStore",
    "DEFAULT_INTENT_SESSION_TTL_SECONDS",
    "IntentSessionCapacityExhausted",
    "IntentSessionTurnLimitReached",
    "IntentSessionUnavailable",
    "MAX_INTENT_SESSIONS",
    "MAX_INTENT_SESSION_TURNS",
]
