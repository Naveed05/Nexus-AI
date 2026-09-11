from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    step_id: str
    objective: str
    status: StepStatus = StepStatus.PENDING
    result: Any | None = None
    observation: Any | None = None
    error: str | None = None
    attempts: int = 0
    depends_on: tuple[str, ...] = ()
    execution_required: bool = True


@dataclass
class AgentState:
    task_id: UUID
    objective: str
    steps: list[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    artifacts: list[str] = field(default_factory=list)
    verification_passed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def current_step(self) -> PlanStep | None:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def completed(self) -> bool:
        return bool(self.steps) and all(
            step.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
            for step in self.steps
        )

    def advance(self) -> None:
        if self.current_step_index < len(self.steps):
            self.current_step_index += 1

    def step_by_id(self, step_id: str) -> PlanStep:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(f"Unknown plan step: {step_id}")

    def dependencies_completed(self, step: PlanStep) -> bool:
        return all(
            self.step_by_id(dependency).status
            in {StepStatus.COMPLETED, StepStatus.SKIPPED}
            for dependency in step.depends_on
        )
