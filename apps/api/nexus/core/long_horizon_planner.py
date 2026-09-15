from dataclasses import dataclass

from nexus.core.goal_manager import Goal


@dataclass(frozen=True)
class HorizonMilestone:
    """A bounded milestone in a long-horizon execution plan."""

    milestone_id: str
    objective: str
    depends_on: tuple[str, ...] = ()
    horizon: int = 0


@dataclass(frozen=True)
class LongHorizonPlan:
    """Dependency-aware milestones derived from a goal."""

    goal_id: str
    milestones: tuple[HorizonMilestone, ...]


class LongHorizonPlanner:
    """Convert a goal into deterministic, dependency-aware milestones."""

    def build(self, goal: Goal) -> LongHorizonPlan:
        if goal.status == "cancelled":
            raise ValueError("Cancelled goals cannot be planned")

        if goal.milestones:
            items = goal.milestones
        else:
            items = (goal.objective.strip(),)

        milestones: list[HorizonMilestone] = []
        previous: str | None = None
        for index, objective in enumerate(items, start=1):
            milestone_id = f"m{index}"
            dependencies = (previous,) if previous else ()
            milestones.append(
                HorizonMilestone(
                    milestone_id=milestone_id,
                    objective=objective,
                    depends_on=dependencies,
                    horizon=index,
                )
            )
            previous = milestone_id

        return LongHorizonPlan(goal_id=str(goal.goal_id), milestones=tuple(milestones))
