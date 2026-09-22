from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from threading import RLock
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
    """Append-only, hash-chained collaboration events for inspection and replay."""

    def __init__(self, max_events: int = 2048) -> None:
        if max_events < 1:
            raise ValueError("max_events must be at least 1")
        self.max_events = max_events
        self._events: list[CollaborationAuditEvent] = []
        self._lock = RLock()

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

    def append(self, event_type: str, actor: str, payload: dict[str, Any]) -> CollaborationAuditEvent:
        event_type = event_type.strip()
        actor = actor.strip()
        if not event_type or not actor:
            raise ValueError("event_type and actor cannot be empty")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        with self._lock:
            if len(self._events) >= self.max_events:
                raise ValueError("audit log capacity exceeded")
            sequence = len(self._events) + 1
            created_at = datetime.now(timezone.utc)
            previous_hash = self._events[-1].event_hash if self._events else "GENESIS"
            canonical = self._canonical(
                sequence,
                event_type,
                actor,
                payload,
                created_at.isoformat(),
                previous_hash,
            )
            event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            event = CollaborationAuditEvent(
                sequence,
                event_type,
                actor,
                dict(payload),
                created_at,
                previous_hash,
                event_hash,
            )
            self._events.append(event)
            return event

    def list(self, limit: int = 100) -> tuple[CollaborationAuditEvent, ...]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        with self._lock:
            return tuple(self._events[-min(limit, self.max_events):])

    def verify(self) -> tuple[bool, str | None]:
        with self._lock:
            previous = "GENESIS"
            for expected_sequence, event in enumerate(self._events, start=1):
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
        with self._lock:
            self._events.clear()


collaboration_audit = CollaborationAuditLog()
