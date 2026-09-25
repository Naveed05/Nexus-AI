from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any
from uuid import UUID, uuid4


class EventType(str, Enum):
    TASK_STARTED = "task_started"
    PLAN_CREATED = "plan_created"
    MODEL_ROUTED = "model_routed"
    STEP_STARTED = "step_started"
    TOOL_SELECTED = "tool_selected"
    TOOL_AUTHORIZATION = "tool_authorization"
    TOOL_CALLED = "tool_called"
    STEP_FAILED = "step_failed"
    RETRY_SCHEDULED = "retry_scheduled"
    EXECUTION_RECOVERED = "execution_recovered"
    STEP_COMPLETED = "step_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


@dataclass(frozen=True)
class ExecutionEvent:
    event_type: EventType
    task_id: UUID
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        # The engine already models the execution lifecycle as immutable events.
        # Persisting them at creation makes the same lifecycle queryable after restart.
        store = globals().get("event_store")
        if store is not None:
            store.append(self)


@dataclass(frozen=True)
class EventRecord:
    event_id: UUID
    event_type: str
    task_id: UUID
    message: str
    data: dict[str, Any]
    timestamp: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "task_id": str(self.task_id),
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class EventStore:
    """Durable execution-event spine used by the engine and operational tooling."""

    def __init__(self, storage_path: str | None = None) -> None:
        self._path = storage_path
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        if storage_path:
            os.makedirs(os.path.dirname(os.path.abspath(storage_path)) or ".", exist_ok=True)
            self._connection = sqlite3.connect(storage_path, check_same_thread=False)
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS execution_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )"""
            )
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_execution_events_task ON execution_events(task_id, timestamp)")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_execution_events_type ON execution_events(event_type, timestamp)")
            self._connection.commit()

    def append(self, event: ExecutionEvent) -> EventRecord:
        record = EventRecord(uuid4(), event.event_type.value, event.task_id, event.message, dict(event.data), event.timestamp)
        if self._connection is not None:
            with self._lock:
                self._connection.execute(
                    "INSERT INTO execution_events VALUES (?,?,?,?,?,?)",
                    (
                        str(record.event_id),
                        record.event_type,
                        str(record.task_id),
                        record.message,
                        json.dumps(record.data, default=str),
                        record.timestamp.isoformat(),
                    ),
                )
                self._connection.commit()
        return record

    def list(self, *, task_id: UUID | None = None, event_type: str | None = None, limit: int = 500) -> tuple[EventRecord, ...]:
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        if self._connection is None:
            return ()
        query = "SELECT * FROM execution_events"
        clauses: list[str] = []
        params: list[str] = []
        if task_id is not None:
            clauses.append("task_id=?")
            params.append(str(task_id))
        if event_type is not None:
            clauses.append("event_type=?")
            params.append(event_type)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(str(limit))
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return tuple(
            EventRecord(
                UUID(row[0]),
                row[1],
                UUID(row[2]),
                row[3],
                json.loads(row[4] or "{}"),
                datetime.fromisoformat(row[5]),
            )
            for row in rows
        )

    def task_timeline(self, task_id: UUID, *, limit: int = 500) -> list[dict[str, Any]]:
        return [record.as_dict() for record in self.list(task_id=task_id, limit=limit)]

    def summary(self, *, task_id: UUID | None = None) -> dict[str, Any]:
        records = self.list(task_id=task_id, limit=5000)
        counts: dict[str, int] = {}
        for record in records:
            counts[record.event_type] = counts.get(record.event_type, 0) + 1
        return {
            "task_id": str(task_id) if task_id else None,
            "event_count": len(records),
            "event_types": counts,
            "first_event_at": records[0].timestamp.isoformat() if records else None,
            "last_event_at": records[-1].timestamp.isoformat() if records else None,
        }


event_store = EventStore(os.getenv("NEXUS_EVENT_STORAGE_PATH", ".nexus/events.sqlite3"))
