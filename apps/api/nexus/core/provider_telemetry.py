from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderTelemetryEvent:
    """Immutable, vendor-neutral record of a model provider attempt."""
    provider: str
    model_id: str
    success: bool
    duration_ms: float
    failure_kind: str | None = None
    fallback_index: int = 0

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model_id.strip():
            raise ValueError("provider and model_id cannot be blank")
        if self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")
        if self.fallback_index < 0:
            raise ValueError("fallback_index cannot be negative")

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "failure_kind": self.failure_kind,
            "fallback_index": self.fallback_index,
        }


class ProviderTelemetry:
    """In-memory telemetry sink with deterministic aggregate snapshots."""

    def __init__(self) -> None:
        self._events: list[ProviderTelemetryEvent] = []

    def record(self, event: ProviderTelemetryEvent) -> None:
        self._events.append(event)

    def events(self) -> tuple[ProviderTelemetryEvent, ...]:
        return tuple(self._events)

    def snapshot(self) -> dict[str, Any]:
        events = self._events
        successes = sum(event.success for event in events)
        failures = len(events) - successes
        durations = [event.duration_ms for event in events]
        return {
            "total_requests": len(events),
            "successes": successes,
            "failures": failures,
            "success_rate": successes / len(events) if events else 0.0,
            "total_duration_ms": sum(durations),
            "average_duration_ms": sum(durations) / len(durations) if durations else 0.0,
            "providers": tuple(sorted({event.provider for event in events})),
        }
