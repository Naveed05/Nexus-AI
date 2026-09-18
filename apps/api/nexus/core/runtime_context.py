from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeContext:
    """Immutable context envelope propagated across runtime stages."""

    task_id: str
    objective: str
    workspace_id: str | None = None
    stage: str = "created"
    step_id: str | None = None
    attempt: int = 0
    assignments: tuple[Any, ...] = ()
    metadata: Mapping[str, Any] = ()

    def for_stage(self, stage: str, *, step_id: str | None = None, attempt: int | None = None) -> "RuntimeContext":
        if not stage.strip():
            raise ValueError("stage cannot be empty")
        next_attempt = self.attempt if attempt is None else attempt
        if next_attempt < 0:
            raise ValueError("attempt cannot be negative")
        return RuntimeContext(self.task_id, self.objective, self.workspace_id, stage.strip(), step_id, next_attempt, self.assignments, self.metadata)
