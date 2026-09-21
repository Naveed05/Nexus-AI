from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class ExecutionMetric:
    run_id: str
    model: str
    duration_ms: float
    verification_passed: bool


class ExecutionMetrics:
    """Bounded in-process metric samples for operational export."""

    def __init__(self, max_samples: int = 1000) -> None:
        if max_samples < 1:
            raise ValueError("max_samples must be at least 1")
        self._max_samples = max_samples
        self._samples: list[ExecutionMetric] = []
        self._lock = RLock()

    def record(self, sample: ExecutionMetric) -> None:
        with self._lock:
            self._samples.append(sample)
            if len(self._samples) > self._max_samples:
                del self._samples[:-self._max_samples]

    def snapshot(self) -> tuple[ExecutionMetric, ...]:
        with self._lock:
            return tuple(self._samples)

    def summary(self) -> dict[str, float | int]:
        samples = self.snapshot()
        if not samples:
            return {"count": 0, "verification_pass_rate": 0.0, "avg_duration_ms": 0.0}
        return {
            "count": len(samples),
            "verification_pass_rate": round(sum(item.verification_passed for item in samples) / len(samples), 3),
            "avg_duration_ms": round(sum(item.duration_ms for item in samples) / len(samples), 3),
        }
