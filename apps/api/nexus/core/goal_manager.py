from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class Goal:
    """Persistent-friendly representation of a long-lived objective."""

    goal_id: UUID = field(default_factory=uuid4)
    objective: str = ""
    milestones: tuple[str, ...] = ()
    status: str = "pending"
    progress: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("Goal objective cannot be empty")
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError("Goal progress must be between 0 and 1")
        if self.status not in {"pending", "active", "completed", "blocked", "cancelled"}:
            raise ValueError(f"Unsupported goal status: {self.status}")


class GoalManager:
    """Create and advance bounded long-horizon goals without executing work."""

    def create(self, objective: str, milestones: list[str] | tuple[str, ...] = ()) -> Goal:
        clean = tuple(item.strip() for item in milestones if item.strip())
        return Goal(objective=objective.strip(), milestones=clean)

    def activate(self, goal: Goal) -> Goal:
        if goal.status not in {"pending", "blocked"}:
            raise ValueError("Only pending or blocked goals can be activated")
        goal.status = "active"
        return goal

    def update_progress(self, goal: Goal, progress: float) -> Goal:
        if goal.status == "cancelled":
            raise ValueError("Cancelled goals cannot be advanced")
        if not 0.0 <= progress <= 1.0:
            raise ValueError("Goal progress must be between 0 and 1")
        goal.progress = round(progress, 3)
        if progress >= 1.0:
            goal.progress = 1.0
            goal.status = "completed"
        elif goal.status == "pending":
            goal.status = "active"
        return goal
