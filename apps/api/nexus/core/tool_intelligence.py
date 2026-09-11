from dataclasses import dataclass

from nexus.core.state import PlanStep
from nexus.core.task import Task
from nexus.core.tools import ToolRegistry, ToolSpec, tool_registry


@dataclass(frozen=True)
class ToolDecision:
    tool: ToolSpec | None
    score: float
    reasons: tuple[str, ...] = ()


class ToolSelector:
    """Select the safest registered tool that best matches an execution step."""

    _step_preferences: dict[str, tuple[str, ...]] = {
        "inspect_data": ("profile_dataset",),
        "analyze_data": ("analyze_dataset", "baseline_ml"),
        "execute": ("calculator",),
    }

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or tool_registry

    def select(self, task: Task, step: PlanStep) -> ToolDecision:
        preferred = self._step_preferences.get(step.step_id, ())
        candidates = {tool.name: tool for tool in self._registry.all()}

        for index, name in enumerate(preferred):
            tool = candidates.get(name)
            if tool is None:
                continue
            if tool.risk_level == "high" and task.risk_level.value != "high":
                continue
            return ToolDecision(
                tool=tool,
                score=100.0 - index * 10.0,
                reasons=(f"matched plan step '{step.step_id}'",),
            )

        return ToolDecision(
            tool=None,
            score=0.0,
            reasons=(f"no registered tool matches plan step '{step.step_id}'",),
        )


selector = ToolSelector()
