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
    error: str | None = None
    attempts: int = 0


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
