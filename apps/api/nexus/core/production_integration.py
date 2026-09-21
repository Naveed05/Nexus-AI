from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.core.engine import NexusEngine
from nexus.core.execution_queue import ExecutionQueue
from nexus.core.runtime import AgentRun, RunBudget
from nexus.core.task import Task


@dataclass(frozen=True)
class ProductionExecutionResult:
    run: AgentRun
    result: Any


class ProductionExecutionCoordinator:
    """Coordinates durable run creation, queued execution, and completion."""

    def __init__(self, *, queue: ExecutionQueue, runtime: Any, engine: NexusEngine) -> None:
        self._queue = queue
        self._runtime = runtime
        self._engine = engine

    def submit(self, task: Task, *, budget: RunBudget | None = None):
        run = self._runtime.runtime.create_run(task, budget=budget)
        job = self._queue.enqueue(run.run_id)
        return run, job

    def execute_claimed(self, job_id, worker_id: str) -> ProductionExecutionResult:
        job = self._queue.get(job_id)
        if job.worker_id != worker_id or job.status.value != "claimed":
            raise ValueError("job is not claimed by this worker")
        run = self._runtime.runtime.get(job.run_id)
        if run.status.value not in {"created", "running"}:
            raise ValueError("run is not executable")
        task = Task(objective=f"production run {run.run_id}", task_id=run.task_id)
        try:
            completed, result = self._runtime.runtime.run_engine(task, self._engine)
            self._queue.complete(job.job_id)
            return ProductionExecutionResult(completed, result)
        except Exception:
            self._queue.complete(job.job_id, failed=True)
            raise
