"""Single-flight boundary for per-table agent runs."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
import time
from typing import Protocol
from uuid import uuid4


class AgentRunLeaseStore(Protocol):
    """Cross-worker implementations must atomically claim one table/version pair."""

    async def claim(self, table_id: str, state_version: int) -> bool: ...

    async def release(self, table_id: str, state_version: int) -> None: ...


class InMemoryAgentRunLeaseStore:
    """Development implementation. Production must replace this for multi-worker use."""

    def __init__(self) -> None:
        self._claimed: set[tuple[str, int]] = set()
        self._lock = asyncio.Lock()

    async def claim(self, table_id: str, state_version: int) -> bool:
        key = _lease_key(table_id, state_version)
        async with self._lock:
            if key in self._claimed:
                return False
            self._claimed.add(key)
            return True

    async def release(self, table_id: str, state_version: int) -> None:
        key = _lease_key(table_id, state_version)
        async with self._lock:
            self._claimed.discard(key)

    @asynccontextmanager
    async def lease(self, table_id: str, state_version: int) -> AsyncIterator[bool]:
        claimed = await self.claim(table_id, state_version)
        try:
            yield claimed
        finally:
            if claimed:
                await self.release(table_id, state_version)


def _lease_key(table_id: str, state_version: int) -> tuple[str, int]:
    if not table_id:
        raise ValueError("table_id must not be empty")
    if state_version < 0:
        raise ValueError("state_version must be non-negative")
    return table_id, state_version


class SQLiteAgentRunLeaseStore:
    """Cross-worker lease implementation backed by SQLite's atomic write lock."""

    def __init__(self, path: str | Path, *, ttl_seconds: float = 45.0, owner_id: str | None = None) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.path = Path(path)
        self.ttl_seconds = ttl_seconds
        self.owner_id = owner_id or uuid4().hex
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_run_leases (
                    table_id TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    owner_id TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (table_id, state_version)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    async def claim(self, table_id: str, state_version: int) -> bool:
        key = _lease_key(table_id, state_version)
        now = time.time()

        def operation() -> bool:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "DELETE FROM agent_run_leases WHERE expires_at <= ?",
                    (now,),
                )
                try:
                    connection.execute(
                        "INSERT INTO agent_run_leases(table_id, state_version, owner_id, expires_at) VALUES (?, ?, ?, ?)",
                        (*key, self.owner_id, now + self.ttl_seconds),
                    )
                except sqlite3.IntegrityError:
                    connection.rollback()
                    return False
                connection.commit()
                return True

        return await asyncio.to_thread(operation)

    async def release(self, table_id: str, state_version: int) -> None:
        key = _lease_key(table_id, state_version)

        def operation() -> None:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM agent_run_leases WHERE table_id = ? AND state_version = ? AND owner_id = ?",
                    (*key, self.owner_id),
                )

        await asyncio.to_thread(operation)

    @asynccontextmanager
    async def lease(self, table_id: str, state_version: int) -> AsyncIterator[bool]:
        claimed = await self.claim(table_id, state_version)
        try:
            yield claimed
        finally:
            if claimed:
                await self.release(table_id, state_version)
