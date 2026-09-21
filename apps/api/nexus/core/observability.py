from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class RuntimeSnapshot:
    total_runs: int
    completed_runs: int
    failed_runs: int
    cancelled_runs: int
    active_runs: int


class RuntimeObservability:
    """Small deterministic metrics surface for runtime health and dashboards."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._counts = {"total": 0, "completed": 0, "failed": 0, "cancelled": 0, "active": 0}

    def observe(self, status: str) -> None:
        with self._lock:
            self._counts["total"] += 1
            if status in {"running", "created"}:
                self._counts["active"] += 1
            elif status in {"completed", "failed", "cancelled"}:
                self._counts[status] += 1
                self._counts["active"] = max(0, self._counts["active"] - 1)

    def snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            return RuntimeSnapshot(
                self._counts["total"], self._counts["completed"], self._counts["failed"],
                self._counts["cancelled"], self._counts["active"],
            )

    def health(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {"status": "healthy", "active_runs": snapshot.active_runs, "total_runs": snapshot.total_runs}


observability = RuntimeObservability()
