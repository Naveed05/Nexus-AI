from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class OrchestrationEvent:
    """Immutable audit record for one orchestration lifecycle event."""

    event: str
    step_id: str
    timestamp: str
    details: dict[str, Any]


class OrchestrationAudit:
    """Keep a deterministic in-memory audit trail for orchestration decisions."""

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

    def clear(self) -> None:
        self._events.clear()
