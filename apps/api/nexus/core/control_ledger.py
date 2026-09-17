from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .developer_approval import DeveloperApproval
    from .human_control import ControlDecision


_SCHEMA = "nexus-human-control-ledger-v1"


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class ControlEvent:
    """One immutable human-control decision in an append-only hash chain."""
    sequence: int
    action: str
    actor: str
    decision: str
    reason: str
    created_at: str
    previous_hash: str
    event_hash: str

    def payload(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "action": self.action, "actor": self.actor, "decision": self.decision, "reason": self.reason, "created_at": self.created_at, "previous_hash": self.previous_hash}

    @classmethod
    def create(cls, sequence: int, action: str, actor: str, decision: str, reason: str, *, previous_hash: str = "", created_at: str | None = None) -> "ControlEvent":
        if sequence < 1:
            raise ValueError("sequence must be at least 1")
        if not action.strip() or not actor.strip() or not decision.strip() or not reason.strip():
            raise ValueError("action, actor, decision, and reason must not be empty")
        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("created_at must include a timezone offset")
        payload = {"sequence": sequence, "action": action.strip().lower(), "actor": actor.strip(), "decision": decision.strip().lower(), "reason": reason.strip(), "created_at": timestamp, "previous_hash": previous_hash}
        digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        return cls(**payload, event_hash=digest)

    def as_dict(self) -> dict[str, Any]:
        return {**self.payload(), "event_hash": self.event_hash}

    def verify(self) -> bool:
        expected = hashlib.sha256(_canonical(self.payload()).encode("utf-8")).hexdigest()
        return self.event_hash == expected


class ControlLedger:
    """Append-only JSON ledger with schema checks and a tamper-evident hash chain."""
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def append(self, action: str, actor: str, decision: str, reason: str, *, expected_head_hash: str | None = None) -> ControlEvent:
        events = self.load()
        current_head = events[-1].event_hash if events else ""
        if expected_head_hash is not None and expected_head_hash != current_head:
            raise RuntimeError("human control ledger head changed; append aborted")
        event = ControlEvent.create(len(events) + 1, action, actor, decision, reason, previous_hash=current_head)
        self._write((*events, event))
        return event

    def append_decision(self, decision: "ControlDecision", *, actor: str, expected_head_hash: str | None = None) -> ControlEvent:
        if not actor.strip():
            raise ValueError("actor must not be empty")
        reason = decision.reasons[0] if decision.reasons else "human-control decision"
        return self.append(decision.action, actor, "allowed" if decision.allowed else "denied", reason, expected_head_hash=expected_head_hash)

    def append_approval(self, approval: "DeveloperApproval", *, action: str = "patch_execution", expected_head_hash: str | None = None) -> ControlEvent:
        if not action.strip():
            raise ValueError("action must not be empty")
        reason = f"patch_fingerprint={approval.patch_fingerprint}; {approval.reason or 'pending decision'}"
        return self.append(action, approval.actor, approval.status.value, reason, expected_head_hash=expected_head_hash)

    def audit(self, *, action: str | None = None, actor: str | None = None, decision: str | None = None, limit: int | None = None) -> tuple[ControlEvent, ...]:
        """Return validated audit events newest-first with normalized filters."""
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        normalized_action = action.strip().lower() if action is not None else None
        normalized_actor = actor.strip() if actor is not None else None
        normalized_decision = decision.strip().lower() if decision is not None else None
        if action is not None and not normalized_action:
            raise ValueError("action must not be empty")
        if actor is not None and not normalized_actor:
            raise ValueError("actor must not be empty")
        if decision is not None and not normalized_decision:
            raise ValueError("decision must not be empty")
        events = self.load()
        matches = tuple(
            event for event in reversed(events)
            if (normalized_action is None or event.action == normalized_action)
            and (normalized_actor is None or event.actor == normalized_actor)
            and (normalized_decision is None or event.decision == normalized_decision)
        )
        return matches[:limit] if limit is not None else matches

    def head(self) -> ControlEvent | None:
        """Return the validated ledger head, or None for an empty ledger."""
        events = self.load()
        return events[-1] if events else None

    def load(self) -> tuple[ControlEvent, ...]:
        if not self._path.exists():
            return ()
        try:
            decoded = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("invalid human control ledger JSON") from exc
        if not isinstance(decoded, dict) or decoded.get("schema") != _SCHEMA or not isinstance(decoded.get("events"), list):
            raise ValueError("unsupported human control ledger schema")
        events: list[ControlEvent] = []
        previous = ""
        for index, payload in enumerate(decoded["events"], 1):
            if not isinstance(payload, dict):
                raise ValueError("invalid human control ledger event")
            try:
                event = ControlEvent(**payload)
            except TypeError as exc:
                raise ValueError("invalid human control ledger event") from exc
            if event.sequence != index or event.previous_hash != previous or not event.verify():
                raise ValueError("human control ledger integrity check failed")
            events.append(event)
            previous = event.event_hash
        return tuple(events)

    def verify(self) -> bool:
        self.load()
        return True

    def _write(self, events: tuple[ControlEvent, ...]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": _SCHEMA, "events": [event.as_dict() for event in events]}
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(_canonical(payload) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self._path)
            try:
                directory_fd = os.open(self._path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
