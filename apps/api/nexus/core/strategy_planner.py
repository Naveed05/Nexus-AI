from dataclasses import dataclass

from nexus.core.orchestrator import TaskPlan
from nexus.core.strategy_selector import StrategySelection


@dataclass(frozen=True)
class StrategyPlan:
    """Execution-safe strategy guidance derived from a selected strategy."""

    strategy: str
    priorities: tuple[str, ...]
    safeguards: tuple[str, ...]


class StrategyAwarePlanner:
    """Translate a strategy choice into bounded planning guidance without mutation."""

    def adapt(self, plan: TaskPlan, selection: StrategySelection) -> StrategyPlan:
        priorities = tuple(step.step_id for step in plan.steps)
        safeguards: list[str] = []

        if selection.strategy == "cautious":
            safeguards.extend(("verify each stage before progression", "preserve recovery checkpoints"))
        elif selection.strategy == "review":
            safeguards.extend(("review plan quality before execution", "re-validate assumptions"))
        elif selection.strategy == "direct":
            safeguards.append("retain final verification gate")
        else:
            safeguards.append("retain verification before completion")

        return StrategyPlan(
            strategy=selection.strategy,
            priorities=priorities,
            safeguards=tuple(safeguards),
        )
