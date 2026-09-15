from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from nexus.core.planner import TaskPlanner
from nexus.core.state import PlanStep, StepStatus
from nexus.core.task import Task


@dataclass(frozen=True)
class TaskPlan:
    """Validated decomposition of a task into dependency-aware execution steps."""

    task_id: UUID
    objective: str
    steps: tuple[PlanStep, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Task plan step IDs must be unique")
        known = set(step_ids)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(
                    f"Step '{step.step_id}' has unknown dependencies: {sorted(missing)}"
                )
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()
        by_id = {step.step_id: step for step in self.steps}

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("Task plan dependencies must be acyclic")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in by_id[step_id].depends_on:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in by_id:
            visit(step_id)

    def step_by_id(self, step_id: str) -> PlanStep:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(f"Unknown plan step: {step_id}")

    def ready_steps(self) -> tuple[PlanStep, ...]:
        """Return pending steps whose dependencies are all completed or skipped."""
        return tuple(
            step
            for step in self.steps
            if step.status == StepStatus.PENDING
            and all(
                self.step_by_id(dependency).status
                in {StepStatus.COMPLETED, StepStatus.SKIPPED}
                for dependency in step.depends_on
            )
        )


class TaskDecomposer:
    """Turns the existing deterministic planner output into a validated task plan."""

    def __init__(self, planner: TaskPlanner | None = None) -> None:
        self._planner = planner or TaskPlanner()

    def decompose(self, task: Task) -> TaskPlan:
        objective = task.objective.strip()
        if not objective:
            raise ValueError("Task objective cannot be empty")
        steps = tuple(self._planner.plan(task))
        if not steps:
            raise ValueError("Task planner returned an empty plan")
        return TaskPlan(
            task_id=task.task_id,
            objective=objective,
            steps=steps,
            metadata={"step_count": len(steps)},
        )


@dataclass
class OrchestratorState:
    """Runtime state for dependency-aware orchestration without executing tools."""

    plan: TaskPlan
    status: str = "ready"
    current_step_id: str | None = None
    history: list[str] = field(default_factory=list)

    def ready_steps(self) -> tuple[PlanStep, ...]:
        return self.plan.ready_steps()

    def start_step(self, step_id: str) -> PlanStep:
        step = self.plan.step_by_id(step_id)
        if step.status != StepStatus.PENDING:
            raise ValueError(f"Step '{step_id}' is not pending")
        if step not in self.ready_steps():
            raise ValueError(f"Step '{step_id}' is not ready")
        step.status = StepStatus.RUNNING
        self.current_step_id = step_id
        self.status = "running"
        self.history.append(f"started:{step_id}")
        return step

    def complete_step(self, step_id: str, result: Any | None = None) -> PlanStep:
        step = self.plan.step_by_id(step_id)
        if step.status != StepStatus.RUNNING:
            raise ValueError(f"Step '{step_id}' is not running")
        step.result = result
        step.status = StepStatus.COMPLETED
        self.history.append(f"completed:{step_id}")
        self.current_step_id = None
        self.status = "completed" if not self.ready_steps() and all(
            item.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
            for item in self.plan.steps
        ) else "ready"
        return step

    def fail_step(self, step_id: str, error: str) -> PlanStep:
        step = self.plan.step_by_id(step_id)
        if step.status != StepStatus.RUNNING:
            raise ValueError(f"Step '{step_id}' is not running")
        if not error.strip():
            raise ValueError("error cannot be empty")
        step.error = error.strip()
        step.status = StepStatus.FAILED
        self.history.append(f"failed:{step_id}")
        self.current_step_id = None
        self.status = "failed"
        return step
