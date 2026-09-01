"""Small process-local sliding-window limiter for REST mutation requests."""

from collections import defaultdict, deque
from math import ceil
from pathlib import Path
import sqlite3
from threading import RLock
import time


WINDOW_SECONDS = 60.0
DEFAULT_MAX_MUTATIONS_PER_MINUTE = 600


class MutationRateLimiter:
    """Bound mutation bursts without adding a shared infrastructure dependency."""

    def __init__(self, max_requests: int, *, clock=time.monotonic) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be a positive integer")
        self.max_requests = max_requests
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def allow(self, client_key: str) -> tuple[bool, int]:
        """Return whether a request is allowed and a useful retry delay."""
        now = self._clock()
        with self._lock:
            requests = self._requests[client_key]
            cutoff = now - WINDOW_SECONDS
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.max_requests:
                retry_after = max(1, ceil(requests[0] + WINDOW_SECONDS - now))
                return False, retry_after
            requests.append(now)
            return True, 0


class SQLiteMutationRateLimiter:
    """Cross-process sliding-window limiter backed by SQLite.

    SQLite is deliberately used as a small coordination primitive rather than
    as the table repository.  ``BEGIN IMMEDIATE`` serializes the prune/count/
    insert decision, so two ASGI workers sharing the same file cannot both
    admit a request past the configured budget.
    """

    def __init__(
        self,
        path: str | Path,
        max_requests: int,
        *,
        clock=time.time,
        busy_timeout_seconds: float = 5.0,
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be a positive integer")
        if busy_timeout_seconds <= 0:
            raise ValueError("busy_timeout_seconds must be positive")
        self.path = Path(path)
        self.max_requests = max_requests
        self._clock = clock
        self._busy_timeout_seconds = busy_timeout_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mutation_rate_limit (
                    client_key TEXT NOT NULL,
                    occurred_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mutation_rate_limit_key_time "
                "ON mutation_rate_limit(client_key, occurred_at)"
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=self._busy_timeout_seconds,
            isolation_level=None,
        )
        connection.execute(
            f"PRAGMA busy_timeout = {int(self._busy_timeout_seconds * 1000)}"
        )
        return connection

    def allow(self, client_key: str) -> tuple[bool, int]:
        """Return whether a request is allowed and a useful retry delay."""
        now = float(self._clock())
        cutoff = now - WINDOW_SECONDS
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM mutation_rate_limit WHERE occurred_at <= ?",
                    (cutoff,),
                )
                row = connection.execute(
                    "SELECT occurred_at FROM mutation_rate_limit "
                    "WHERE client_key = ? ORDER BY occurred_at LIMIT 1",
                    (client_key,),
                ).fetchone()
                count = connection.execute(
                    "SELECT COUNT(*) FROM mutation_rate_limit WHERE client_key = ?",
                    (client_key,),
                ).fetchone()[0]
                if count >= self.max_requests and row is not None:
                    retry_after = max(1, ceil(float(row[0]) + WINDOW_SECONDS - now))
                    connection.execute("COMMIT")
                    return False, retry_after
                connection.execute(
                    "INSERT INTO mutation_rate_limit(client_key, occurred_at) VALUES (?, ?)",
                    (client_key, now),
                )
                connection.execute("COMMIT")
                return True, 0
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()


__all__ = (
    "DEFAULT_MAX_MUTATIONS_PER_MINUTE",
    "MutationRateLimiter",
    "SQLiteMutationRateLimiter",
    "WINDOW_SECONDS",
)
