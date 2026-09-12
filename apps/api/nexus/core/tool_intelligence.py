from dataclasses import dataclass

from nexus.core.permissions import PermissionDecision, PermissionPolicy
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
        "research": ("search_knowledge",),
        "synthesize": ("search_knowledge",),
        "execute": ("calculator",),
    }

    _dataset_step_preferences: dict[str, tuple[str, ...]] = {
        "inspect_data": ("profile_dataset_by_id", "profile_dataset"),
        "analyze_data": ("analyze_dataset_by_id", "analyze_dataset", "baseline_ml"),
    }

    def __init__(self, registry: ToolRegistry | None = None, permission_policy: PermissionPolicy | None = None) -> None:
        self._registry = registry or tool_registry
        self._permission_policy = permission_policy or PermissionPolicy()

    @staticmethod
    def _has_dataset_reference(task: Task) -> bool:
        return "dataset_id" in (task.context or "").lower()

    def select(self, task: Task, step: PlanStep) -> ToolDecision:
        if self._has_dataset_reference(task):
            preferred = self._dataset_step_preferences.get(step.step_id, self._step_preferences.get(step.step_id, ()))
        else:
            preferred = self._step_preferences.get(step.step_id, ())

        candidates = {tool.name: tool for tool in self._registry.all()}
        rejected: list[str] = []
        for index, name in enumerate(preferred):
            tool = candidates.get(name)
            if tool is None:
                rejected.append(f"{name} is not registered")
                continue
            permission = self._permission_policy.decide(tool, task.risk_level)
            if permission != PermissionDecision.ALLOW:
                rejected.append(f"{name} blocked by permission policy ({permission.value})")
                continue
            reasons = [f"matched plan step '{step.step_id}'"]
            if self._has_dataset_reference(task):
                reasons.append("dataset reference detected in task context")
            if index == 0:
                reasons.append("highest-priority compatible tool")
            if rejected:
                reasons.append(f"skipped {len(rejected)} incompatible candidate(s)")
            return ToolDecision(tool=tool, score=100.0 - index * 10.0, reasons=tuple(reasons))

        reasons = [f"no registered tool matches plan step '{step.step_id}'"]
        if rejected:
            reasons.append("; ".join(rejected))
        return ToolDecision(tool=None, score=0.0, reasons=tuple(reasons))


selector = ToolSelector()
