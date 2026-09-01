"""Small optional cross-process event bus for table WebSocket fanout.

The in-process connection registry remains the fast path.  When configured,
``SQLiteEventBus`` gives separate ASGI workers a durable, ordered stream of
public table events.  It carries no private profile data or access tokens;
state events only carry a table/version hint and the receiving worker projects
the current state for each connected viewer before sending it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Protocol


class EventBus(Protocol):
    def publish(self, *, channel: str, payload: dict[str, Any]) -> int:
        """Append one public event and return its monotonically increasing ID."""

    def read_since(self, *, cursor: int, limit: int = 100) -> list["BusEvent"]:
        """Read a bounded ordered batch strictly after ``cursor``."""


@dataclass(frozen=True)
class BusEvent:
    event_id: int
    channel: str
    payload: dict[str, Any]


class SQLiteEventBus:
    """SQLite-backed ordered event log suitable for a small multi-worker app."""

    def __init__(self, path: str | Path, *, busy_timeout_seconds: float = 5.0) -> None:
        if busy_timeout_seconds <= 0:
            raise ValueError("busy_timeout_seconds must be positive")
        self.path = Path(path)
        self._busy_timeout_seconds = busy_timeout_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS table_event_bus (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL DEFAULT (unixepoch('subsec'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_table_event_bus_channel_id "
                "ON table_event_bus(channel, event_id)"
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

    def publish(self, *, channel: str, payload: dict[str, Any]) -> int:
        if not channel.strip():
            raise ValueError("event bus channel must be non-empty")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 256 * 1024:
            raise ValueError("event bus payload is too large")
        connection = self._connect()
        try:
            cursor = connection.execute(
                "INSERT INTO table_event_bus(channel, payload) VALUES (?, ?)",
                (channel, encoded),
            )
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def read_since(self, *, cursor: int, limit: int = 100) -> list[BusEvent]:
        if cursor < 0:
            raise ValueError("event bus cursor must be non-negative")
        if limit <= 0 or limit > 1000:
            raise ValueError("event bus limit must be between 1 and 1000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT event_id, channel, payload FROM table_event_bus "
                "WHERE event_id > ? ORDER BY event_id LIMIT ?",
                (cursor, limit),
            ).fetchall()
        finally:
            connection.close()
        events: list[BusEvent] = []
        for event_id, channel, encoded in rows:
            try:
                payload = json.loads(encoded)
            except (TypeError, json.JSONDecodeError) as error:
                raise ValueError("event bus contains invalid JSON") from error
            if not isinstance(payload, dict):
                raise ValueError("event bus payload must be an object")
            events.append(BusEvent(int(event_id), str(channel), payload))
        return events

    def latest_id(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COALESCE(MAX(event_id), 0) FROM table_event_bus"
            ).fetchone()
        finally:
            connection.close()
        return int(row[0]) if row is not None else 0

    def trim_before(self, *, event_id: int) -> int:
        """Remove old events after every consumer has advanced past them."""
        if event_id < 0:
            raise ValueError("event bus event_id must be non-negative")
        connection = self._connect()
        try:
            cursor = connection.execute(
                "DELETE FROM table_event_bus WHERE event_id < ?", (event_id,)
            )
            return int(cursor.rowcount)
        finally:
            connection.close()


__all__ = ("BusEvent", "EventBus", "SQLiteEventBus")
