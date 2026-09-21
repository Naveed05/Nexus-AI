from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import UUID

from nexus.core.engine import NexusEngine
from nexus.core.runtime import AgentRun, AgentRuntime, RunBudget, RunStatus
from nexus.core.task import Task


@dataclass(frozen=True)
class ProductionRunPolicy:
    """Operational limits for the production runtime boundary."""

    max_concurrent_runs: int = 4

    def __post_init__(self) -> None:
        if self.max_concurrent_runs < 1:
            raise ValueError("max_concurrent_runs must be at least 1")


class ProductionRuntime:
    """Durable, idempotency-aware execution boundary for NEXUS production runs.

    This layer deliberately keeps queue infrastructure out of the core runtime.
    It provides the production contract that a future worker/queue adapter can
    implement without changing AgentRuntime semantics.
    """

    def __init__(
        self,
        *,
        store_path: str,
        engine: NexusEngine | None = None,
        policy: ProductionRunPolicy | None = None,
    ) -> None:
        self._runtime = AgentRuntime(store_path=store_path)
        self._engine = engine or NexusEngine()
        self._policy = policy or ProductionRunPolicy()
        self._lock = RLock()
        self._active = 0
        self._inflight_keys: set[str] = set()

    @property
    def runtime(self) -> AgentRuntime:
        return self._runtime

    def _find_idempotent(self, key: str) -> AgentRun | None:
        for run in self._runtime.list_runs():
            if run.metadata.get("idempotency_key") == key:
                return run
        return None

    def start(
        self,
        task: Task,
        *,
        idempotency_key: str | None = None,
        budget: RunBudget | None = None,
    ) -> tuple[AgentRun, Any]:
        """Execute one production run, rejecting duplicate or overloaded starts."""
        if idempotency_key is not None and not idempotency_key.strip():
            raise ValueError("idempotency_key cannot be empty")

        with self._lock:
            if idempotency_key:
                if idempotency_key in self._inflight_keys:
                    raise ValueError(f"run already exists for idempotency key: {idempotency_key}")
                existing = self._find_idempotent(idempotency_key)
                if existing is not None:
                    raise ValueError(f"run already exists for idempotency key: {idempotency_key}")
            if self._active >= self._policy.max_concurrent_runs:
                raise RuntimeError("production runtime concurrency limit reached")
            if idempotency_key:
                self._inflight_keys.add(idempotency_key)
            self._active += 1

        try:
            run, result = self._runtime.run_engine(task, self._engine, budget=budget)
            if idempotency_key:
                run.metadata["idempotency_key"] = idempotency_key
                # Persist the final metadata without changing lifecycle state.
                self._runtime._persist(run)
            return run, result
        finally:
            with self._lock:
                self._active -= 1
                if idempotency_key:
                    self._inflight_keys.discard(idempotency_key)

    def status(self, run_id: UUID) -> AgentRun:
        """Return durable run state, including runs created by another process."""
        local = self._runtime.get(run_id)
        return local

    def list_runs(self) -> tuple[AgentRun, ...]:
        return self._runtime.list_runs()

    def health(self) -> dict[str, Any]:
        with self._lock:
            active = self._active
        return {
            "status": "ready",
            "active_runs": active,
            "max_concurrent_runs": self._policy.max_concurrent_runs,
            "capacity_available": max(0, self._policy.max_concurrent_runs - active),
        }
