import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OrchestrationEvent:
    """Immutable audit record for one orchestration lifecycle event."""

    event: str
    step_id: str
    timestamp: str
    details: dict[str, Any]


class OrchestrationAudit:
    """Keep a queryable audit trail with optional durable JSON persistence."""

    def __init__(self) -> None:
        self._events: list[OrchestrationEvent] = []

    def record(self, event: str, step_id: str, **details: Any) -> OrchestrationEvent:
        event_name = event.strip()
        step = step_id.strip()
        if not event_name:
            raise ValueError("event cannot be empty")
        if not step:
            raise ValueError("step_id cannot be empty")
        entry = OrchestrationEvent(
            event=event_name,
            step_id=step,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=dict(sorted(details.items())),
        )
        self._events.append(entry)
        return entry

    def events(self) -> tuple[OrchestrationEvent, ...]:
        return tuple(self._events)

    def query(
        self,
        event: str | None = None,
        step_id: str | None = None,
    ) -> tuple[OrchestrationEvent, ...]:
        event_name = event.strip() if event is not None else None
        step = step_id.strip() if step_id is not None else None
        return tuple(
            item
            for item in self._events
            if (event_name is None or item.event == event_name)
            and (step is None or item.step_id == step)
        )

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "event": item.event,
                "step_id": item.step_id,
                "timestamp": item.timestamp,
                "details": item.details,
            }
            for item in self._events
        ]
        target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return target

    def load(self, path: str | Path) -> tuple[OrchestrationEvent, ...]:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("audit checkpoint must contain a list of events")
        restored = tuple(
            OrchestrationEvent(
                event=str(item["event"]),
                step_id=str(item["step_id"]),
                timestamp=str(item["timestamp"]),
                details=dict(item.get("details", {})),
            )
            for item in payload
        )
        self._events = list(restored)
        return restored

    def clear(self) -> None:
        self._events.clear()
