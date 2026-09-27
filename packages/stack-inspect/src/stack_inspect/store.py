"""Append-only SQLite log of events."""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from stack_inspect.model import GraphEvent


class EventLog:
    """Append-only store. Graphs are always derived from it."""

    def __init__(self, path: Path) -> None:
        """Open or create the log at ``path``."""
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                ts REAL NOT NULL,
                body TEXT NOT NULL
            )
            """,
        )
        self._connection.commit()

    def append(self, event: GraphEvent) -> None:
        """Store ``event``. A repeated id is ignored so retries are safe."""
        body = json.dumps(event)
        with self._lock:
            self._connection.execute(
                "INSERT OR IGNORE INTO events (id, trace_id, ts, body) VALUES (?, ?, ?, ?)",
                (event["id"], event["traceId"], event["ts"], body),
            )
            self._connection.commit()

    def all_events(self) -> list[GraphEvent]:
        """Return every event in time order."""
        with self._lock:
            rows = self._connection.execute("SELECT body FROM events ORDER BY ts, id").fetchall()
        return [json.loads(row[0]) for row in rows]

    def clear(self) -> None:
        """Delete every event. Used by tests between scenarios."""
        with self._lock:
            self._connection.execute("DELETE FROM events")
            self._connection.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._connection.close()
