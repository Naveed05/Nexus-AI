from __future__ import annotations

from dataclasses import dataclass

from nexus.core.router import RoutingDecision, TaskRouter
from nexus.core.state import PlanStep
from nexus.core.task import Task
from nexus.core.tool_selector import ToolDecision, ToolSelector


@dataclass(frozen=True)
class ProductionExecutionPlan:
    routing: RoutingDecision
    tools: tuple[ToolDecision, ...]
    capability_safe: bool
    reasons: tuple[str, ...]


class ProductionPlanner:
    """Build an explainable model/tool execution plan before work starts."""

    def __init__(self, router: TaskRouter | None = None, tool_selector: ToolSelector | None = None) -> None:
        self._router = router or TaskRouter()
        self._tools = tool_selector or ToolSelector()

    def build(self, task: Task, steps: tuple[PlanStep, ...] = ()) -> ProductionExecutionPlan:
        routing = self._router.decide(task)
        decisions = tuple(self._tools.decide(step) for step in steps)
        missing = [
            decision
            for decision in decisions
            if decision.tool is None
        ]
        safe = not missing
        reasons = list(routing.reasons)
        if decisions:
            reasons.append(f"evaluated {len(decisions)} executable tool decisions")
        if missing:
            reasons.append("one or more steps have no compatible tool")
        return ProductionExecutionPlan(routing, decisions, safe, tuple(reasons))
