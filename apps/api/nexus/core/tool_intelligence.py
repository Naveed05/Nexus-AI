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
    required_capabilities: frozenset[str] = frozenset()
    matched_capabilities: frozenset[str] = frozenset()


class ToolSelector:
    """Select a compatible tool using explicit capabilities and policy constraints."""

    _step_preferences: dict[str, tuple[str, ...]] = {
        "inspect_data": ("profile_dataset",),
        "analyze_data": ("analyze_dataset", "baseline_ml"),
        "research": ("research_knowledge", "search_knowledge"),
        "synthesize": (),
        "execute": ("calculator",),
    }

    _dataset_step_preferences: dict[str, tuple[str, ...]] = {
        "inspect_data": ("profile_dataset_by_id", "profile_dataset"),
        "analyze_data": ("analyze_dataset_by_id", "analyze_dataset", "baseline_ml"),
    }

    _step_capabilities: dict[str, frozenset[str]] = {
        "inspect_data": frozenset({"data_profiling"}),
        "analyze_data": frozenset({"data_analysis"}),
        "research": frozenset({"research"}),
        "execute": frozenset({"calculation"}),
        "synthesize": frozenset(),
    }

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        permission_policy: PermissionPolicy | None = None,
    ) -> None:
        self._registry = registry or tool_registry
        self._permission_policy = permission_policy or PermissionPolicy()

    @staticmethod
    def _has_dataset_reference(task: Task) -> bool:
        return "dataset_id" in (task.context or "").lower()

    @staticmethod
    def _normalized_task_capabilities(task: Task) -> frozenset[str]:
        return frozenset(value.strip().lower() for value in task.capabilities if value.strip())

    def _required_capabilities(self, task: Task, step: PlanStep) -> frozenset[str]:
        required = set(self._step_capabilities.get(step.step_id, frozenset()))
        task_capabilities = self._normalized_task_capabilities(task)
        if task_capabilities:
            # Explicit task capabilities refine selection only when they are
            # represented by the tool registry. Unknown capabilities remain
            # useful metadata without making legacy steps impossible to run.
            known = set(self._registry.capabilities())
            required.update(task_capabilities & known)
        return frozenset(required)

    def select(self, task: Task, step: PlanStep) -> ToolDecision:
        if self._has_dataset_reference(task):
            preferred = self._dataset_step_preferences.get(
                step.step_id,
                self._step_preferences.get(step.step_id, ()),
            )
        else:
            preferred = self._step_preferences.get(step.step_id, ())

        required = self._required_capabilities(task, step)
        candidates = {tool.name: tool for tool in self._registry.all()}
        rejected: list[str] = []
        ranked: list[tuple[float, int, ToolSpec, frozenset[str]]] = []

        for index, name in enumerate(preferred):
            tool = candidates.get(name)
            if tool is None:
                rejected.append(f"{name} is not registered")
                continue
            permission = self._permission_policy.decide(tool, task.risk_level)
            if permission != PermissionDecision.ALLOW:
                rejected.append(f"{name} blocked by permission policy ({permission.value})")
                continue
            if tool.capabilities and not required.issubset(tool.capabilities):
                missing = sorted(required - tool.capabilities)
                rejected.append(f"{name} missing capabilities: {', '.join(missing)}")
                continue
            matched = required & tool.capabilities
            score = 100.0 - index * 10.0
            ranked.append((score, index, tool, matched))

        if ranked:
            score, index, tool, matched = max(
                ranked,
                key=lambda item: (item[0], -item[1], item[2].name),
            )
            reasons = [f"matched plan step '{step.step_id}'"]
            if required:
                reasons.append(f"required capabilities: {', '.join(sorted(required))}")
            if matched:
                reasons.append(f"capabilities satisfied: {', '.join(sorted(matched))}")
            if self._has_dataset_reference(task):
                reasons.append("dataset reference detected in task context")
            if index == 0:
                reasons.append("highest-priority compatible tool")
            if rejected:
                reasons.append(f"skipped {len(rejected)} incompatible candidate(s)")
            return ToolDecision(
                tool=tool,
                score=score,
                reasons=tuple(reasons),
                required_capabilities=required,
                matched_capabilities=matched,
            )

        reasons = [f"no registered tool matches plan step '{step.step_id}'"]
        if required:
            reasons.append(f"required capabilities: {', '.join(sorted(required))}")
        if rejected:
            reasons.append("; ".join(rejected))
        return ToolDecision(
            tool=None,
            score=0.0,
            reasons=tuple(reasons),
            required_capabilities=required,
        )


selector = ToolSelector()
