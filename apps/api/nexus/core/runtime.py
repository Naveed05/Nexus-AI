from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Event, RLock
from typing import Any, Callable
from uuid import UUID, uuid4

from nexus.core.task import Task, TaskStatus


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunCancelledError(RuntimeError):
    """Raised when an agent run is cancelled before or during execution."""


class RunBudgetExceededError(RuntimeError):
    """Raised when a run exceeds its configured execution budget."""


@dataclass(frozen=True)
class RunBudget:
    """Hard execution limits owned by the runtime, independent of model vendors."""

    max_steps: int = 32
    max_tool_calls: int = 64
    max_retries: int = 8

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if self.max_tool_calls < 0:
            raise ValueError("max_tool_calls cannot be negative")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")


@dataclass
class AgentRun:
    """Observable lifecycle state for one deterministic NEXUS task run."""

    run_id: UUID = field(default_factory=uuid4)
    task_id: UUID | None = None
    status: RunStatus = RunStatus.CREATED
    task_status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    steps_completed: int = 0
    tool_calls: int = 0
    retries: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds() * 1000


class ExecutionControl:
    """Thread-safe cancellation and budget checks shared by runtime components."""

    def __init__(self, budget: RunBudget | None = None) -> None:
        self.budget = budget or RunBudget()
        self._cancelled = Event()
        self._lock = RLock()
        self._steps = 0
        self._tool_calls = 0
        self._retries = 0

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def steps(self) -> int:
        return self._steps

    @property
    def tool_calls(self) -> int:
        return self._tool_calls

    @property
    def retries(self) -> int:
        return self._retries

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise RunCancelledError("NEXUS agent run was cancelled")

    def consume_step(self) -> None:
        with self._lock:
            self.check_cancelled()
            if self._steps >= self.budget.max_steps:
                raise RunBudgetExceededError("NEXUS step budget exceeded")
            self._steps += 1

    def consume_tool_call(self) -> None:
        with self._lock:
            self.check_cancelled()
            if self._tool_calls >= self.budget.max_tool_calls:
                raise RunBudgetExceededError("NEXUS tool-call budget exceeded")
            self._tool_calls += 1

    def consume_retry(self) -> None:
        with self._lock:
            self.check_cancelled()
            if self._retries >= self.budget.max_retries:
                raise RunBudgetExceededError("NEXUS retry budget exceeded")
            self._retries += 1


class AgentRuntime:
    """Own the lifecycle of agent runs while keeping execution implementation-agnostic.

    The runtime is intentionally synchronous at this layer. Async workers, queues,
    and distributed execution can be added later without changing the run contract.
    """

    def __init__(self) -> None:
        self._runs: dict[UUID, AgentRun] = {}
        self._controls: dict[UUID, ExecutionControl] = {}
        self._lock = RLock()

    def create_run(self, task: Task, *, budget: RunBudget | None = None) -> AgentRun:
        run = AgentRun(task_id=task.task_id)
        control = ExecutionControl(budget)
        with self._lock:
            self._runs[run.run_id] = run
            self._controls[run.run_id] = control
        return run

    def get(self, run_id: UUID) -> AgentRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise KeyError(f"Unknown run: {run_id}") from exc

    def control(self, run_id: UUID) -> ExecutionControl:
        with self._lock:
            try:
                return self._controls[run_id]
            except KeyError as exc:
                raise KeyError(f"Unknown run: {run_id}") from exc

    def cancel(self, run_id: UUID) -> AgentRun:
        run = self.get(run_id)
        self.control(run_id).cancel()
        if run.status in {RunStatus.CREATED, RunStatus.RUNNING}:
            run.status = RunStatus.CANCELLED
            run.task_status = TaskStatus.CANCELLED
            run.finished_at = datetime.now(timezone.utc)
        return run

    def run(
        self,
        task: Task,
        runner: Callable[[Task, ExecutionControl], Any],
        *,
        budget: RunBudget | None = None,
    ) -> tuple[AgentRun, Any]:
        run = self.create_run(task, budget=budget)
        control = self.control(run.run_id)
        run.status = RunStatus.RUNNING
        run.task_status = TaskStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        try:
            control.check_cancelled()
            result = runner(task, control)
            control.check_cancelled()
            run.steps_completed = control.steps
            run.tool_calls = control.tool_calls
            run.retries = control.retries
            result_task = getattr(result, "task", None)
            result_status = getattr(result_task, "status", None)
            if isinstance(result_status, TaskStatus):
                run.task_status = result_status
            else:
                run.task_status = TaskStatus.COMPLETED
            run.status = (
                RunStatus.COMPLETED
                if run.task_status == TaskStatus.COMPLETED
                else RunStatus.FAILED
            )
            return run, result
        except RunCancelledError as exc:
            run.status = RunStatus.CANCELLED
            run.task_status = TaskStatus.CANCELLED
            run.error = str(exc)
            raise
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.task_status = TaskStatus.FAILED
            run.error = str(exc)
            raise
        finally:
            run.steps_completed = control.steps
            run.tool_calls = control.tool_calls
            run.retries = control.retries
            run.finished_at = datetime.now(timezone.utc)


    def run_engine(self, task: Task, engine: Any, *, budget: RunBudget | None = None) -> tuple[AgentRun, Any]:
        """Run a NEXUS engine through the runtime control boundary."""
        return self.run(task, lambda current_task, control: engine.run(current_task, control=control), budget=budget)

    def list_runs(self) -> tuple[AgentRun, ...]:
        with self._lock:
            return tuple(self._runs.values())


agent_runtime = AgentRuntime()
