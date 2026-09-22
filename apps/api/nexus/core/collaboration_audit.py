from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import RLock
import tempfile
from typing import Any


@dataclass(frozen=True)
class CollaborationAuditEvent:
    sequence: int
    event_type: str
    actor: str
    payload: dict[str, Any]
    created_at: datetime
    previous_hash: str
    event_hash: str


class CollaborationAuditLog:
    """Durable, append-only, hash-chained collaboration events."""

    def __init__(self, path: str = ":memory:", max_events: int = 2048) -> None:
        if max_events < 1:
            raise ValueError("max_events must be at least 1")
        self.path = path
        self.max_events = max_events
        if path == ":memory:":
            fd, ephemeral_path = tempfile.mkstemp(prefix="nexus-audit-", suffix=".sqlite3")
            Path(ephemeral_path).unlink(missing_ok=True)
            import os
            os.close(fd)
            self.path = ephemeral_path
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS collaboration_audit (
                    sequence INTEGER PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE
                )"""
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _canonical(
        sequence: int,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        created_at: str,
        previous_hash: str,
    ) -> str:
        return json.dumps(
            {
                "sequence": sequence,
                "event_type": event_type,
                "actor": actor,
                "payload": payload,
                "created_at": created_at,
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> CollaborationAuditEvent:
        return CollaborationAuditEvent(
            sequence=int(row["sequence"]),
            event_type=row["event_type"],
            actor=row["actor"],
            payload=json.loads(row["payload"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            previous_hash=row["previous_hash"],
            event_hash=row["event_hash"],
        )

    def append(self, event_type: str, actor: str, payload: dict[str, Any]) -> CollaborationAuditEvent:
        event_type = event_type.strip()
        actor = actor.strip()
        if not event_type or not actor:
            raise ValueError("event_type and actor cannot be empty")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT sequence, event_hash FROM collaboration_audit ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if row is not None and int(row["sequence"]) >= self.max_events:
                raise ValueError("audit log capacity exceeded")
            sequence = int(row["sequence"]) + 1 if row is not None else 1
            created_at = datetime.now(timezone.utc)
            previous_hash = row["event_hash"] if row is not None else "GENESIS"
            canonical = self._canonical(
                sequence, event_type, actor, payload, created_at.isoformat(), previous_hash
            )
            event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            conn.execute(
                """INSERT INTO collaboration_audit
                (sequence, event_type, actor, payload, created_at, previous_hash, event_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    sequence,
                    event_type,
                    actor,
                    json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
                    created_at.isoformat(),
                    previous_hash,
                    event_hash,
                ),
            )
            conn.commit()
            return CollaborationAuditEvent(
                sequence, event_type, actor, dict(payload), created_at, previous_hash, event_hash
            )

    def list(
        self,
        limit: int = 100,
        *,
        event_type: str | None = None,
        actor: str | None = None,
        before_sequence: int | None = None,
    ) -> tuple[CollaborationAuditEvent, ...]:
        """Return validated audit events in chronological order within a bounded page."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        normalized_event_type = event_type.strip() if event_type is not None else None
        normalized_actor = actor.strip() if actor is not None else None
        if event_type is not None and not normalized_event_type:
            raise ValueError("event_type cannot be empty")
        if actor is not None and not normalized_actor:
            raise ValueError("actor cannot be empty")
        if before_sequence is not None and before_sequence < 1:
            raise ValueError("before_sequence must be at least 1")
        clauses: list[str] = []
        params: list[Any] = []
        if normalized_event_type is not None:
            clauses.append("event_type = ?")
            params.append(normalized_event_type)
        if normalized_actor is not None:
            clauses.append("actor = ?")
            params.append(normalized_actor)
        if before_sequence is not None:
            clauses.append("sequence < ?")
            params.append(before_sequence)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(min(limit, self.max_events))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM collaboration_audit{where} ORDER BY sequence DESC LIMIT ?", params
            ).fetchall()
        return tuple(self._from_row(row) for row in reversed(rows))

    def stats(self) -> dict[str, Any]:
        """Return bounded operational metadata without exposing storage internals."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS event_count, MAX(sequence) AS head_sequence, MAX(created_at) AS latest_created_at FROM collaboration_audit"
            ).fetchone()
        return {
            "event_count": int(row["event_count"]),
            "capacity": self.max_events,
            "head_sequence": int(row["head_sequence"] or 0),
            "latest_created_at": row["latest_created_at"],
        }

    def verify(self) -> tuple[bool, str | None]:
        events = self.list(limit=self.max_events)
        previous = "GENESIS"
        for expected_sequence, event in enumerate(events, start=1):
            if event.sequence != expected_sequence:
                return False, f"sequence mismatch at event {event.sequence}"
            if event.previous_hash != previous:
                return False, f"hash-chain mismatch at event {event.sequence}"
            canonical = self._canonical(
                event.sequence,
                event.event_type,
                event.actor,
                event.payload,
                event.created_at.isoformat(),
                event.previous_hash,
            )
            expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if event.event_hash != expected_hash:
                return False, f"event hash mismatch at event {event.sequence}"
            previous = event.event_hash
        return True, None

    def clear(self) -> None:
        """Test/support hook; production callers should treat the log as append-only."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM collaboration_audit")
            conn.commit()


collaboration_audit = CollaborationAuditLog()
