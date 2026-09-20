from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Event, RLock
import json
import sqlite3
from pathlib import Path
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


class RunStore:
    """SQLite-backed durable state for agent runs."""

    def __init__(self, path: str = ".nexus/runs.sqlite3") -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY, task_id TEXT, status TEXT NOT NULL,
                    task_status TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    steps_completed INTEGER NOT NULL, tool_calls INTEGER NOT NULL,
                    retries INTEGER NOT NULL, error TEXT, metadata TEXT NOT NULL
                )"""
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    def save(self, run: AgentRun) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO agent_runs
                (run_id, task_id, status, task_status, started_at, finished_at,
                 steps_completed, tool_calls, retries, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(run.run_id), str(run.task_id) if run.task_id else None,
                 run.status.value, run.task_status.value, self._dt(run.started_at),
                 self._dt(run.finished_at), run.steps_completed, run.tool_calls,
                 run.retries, run.error, json.dumps(run.metadata, default=str)),
            )
            conn.commit()

    def load_all(self) -> list[AgentRun]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM agent_runs ORDER BY rowid").fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, run_id: UUID) -> AgentRun | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE run_id = ?", (str(run_id),)).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AgentRun:
        return AgentRun(
            run_id=UUID(row["run_id"]), task_id=UUID(row["task_id"]) if row["task_id"] else None,
            status=RunStatus(row["status"]), task_status=TaskStatus(row["task_status"]),
            started_at=RunStore._parse_dt(row["started_at"]), finished_at=RunStore._parse_dt(row["finished_at"]),
            steps_completed=row["steps_completed"], tool_calls=row["tool_calls"], retries=row["retries"],
            error=row["error"], metadata=json.loads(row["metadata"] or "{}"),
        )


class AgentRuntime:
    """Own the lifecycle of agent runs while keeping execution implementation-agnostic.

    The runtime is intentionally synchronous at this layer. Async workers, queues,
    and distributed execution can be added later without changing the run contract.
    """

    def __init__(self, store_path: str | None = None, *, store: RunStore | None = None) -> None:
        # Library/test runtimes are ephemeral by default. The API supplies an
        # explicit SQLite path when durable run state is required.
        self._store = store or (RunStore(store_path) if store_path is not None else None)
        persisted_runs = self._store.load_all() if self._store is not None else []
        self._runs: dict[UUID, AgentRun] = {run.run_id: run for run in persisted_runs}
        self._controls: dict[UUID, ExecutionControl] = {}
        self._lock = RLock()

    def create_run(self, task: Task, *, budget: RunBudget | None = None) -> AgentRun:
        run = AgentRun(task_id=task.task_id)
        control = ExecutionControl(budget)
        with self._lock:
            self._runs[run.run_id] = run
            self._controls[run.run_id] = control
        self._persist(run)
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
        self._persist(run)
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
            events = getattr(result, "events", None)
            if events is not None:
                run.metadata["event_count"] = len(events)
                run.metadata["event_types"] = [getattr(event.event_type, "value", str(event.event_type)) for event in events]
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
            self._persist(run)
            return run, result
        except RunCancelledError as exc:
            run.status = RunStatus.CANCELLED
            run.task_status = TaskStatus.CANCELLED
            run.error = str(exc)
            self._persist(run)
            raise
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.task_status = TaskStatus.FAILED
            run.error = str(exc)
            self._persist(run)
            raise
        finally:
            run.steps_completed = control.steps
            run.tool_calls = control.tool_calls
            run.retries = control.retries
            run.finished_at = datetime.now(timezone.utc)
            self._persist(run)


    def run_engine(self, task: Task, engine: Any, *, budget: RunBudget | None = None) -> tuple[AgentRun, Any]:
        """Run a NEXUS engine through the runtime control boundary."""
        return self.run(task, lambda current_task, control: engine.run(current_task, control=control), budget=budget)

    def _persist(self, run: AgentRun) -> None:
        if self._store is not None:
            self._store.save(run)

    def list_runs(self) -> tuple[AgentRun, ...]:
        with self._lock:
            return tuple(self._runs.values())


agent_runtime = AgentRuntime()
