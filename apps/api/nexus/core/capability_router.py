from dataclasses import dataclass

from nexus.core.state import PlanStep
from nexus.core.task import Task
from nexus.core.tool_intelligence import ToolDecision, ToolSelector


@dataclass(frozen=True)
class CapabilityDecision:
    """Safe capability selection for one orchestration step."""

    capability: str
    tool: str | None
    score: float
    reasons: tuple[str, ...] = ()


class CapabilityRouter:
    """Map orchestration steps to explicit capabilities and safe registered tools."""

    _step_capabilities: dict[str, str] = {
        "inspect_code": "code_inspection",
        "implement": "code_change",
        "research": "research",
        "synthesize": "synthesis",
        "inspect_data": "data_inspection",
        "analyze_data": "data_analysis",
        "verify": "verification",
        "deliver": "delivery",
        "understand": "context_understanding",
        "execute": "general_execution",
    }

    def __init__(self, selector: ToolSelector | None = None) -> None:
        self._selector = selector or ToolSelector()

    def select(self, task: Task, step: PlanStep) -> CapabilityDecision:
        capability = self._step_capabilities.get(step.step_id, "general_execution")
        tool_decision: ToolDecision = self._selector.select(task, step)
        reasons = [f"matched capability '{capability}'"]
        reasons.extend(tool_decision.reasons)
        return CapabilityDecision(
            capability=capability,
            tool=tool_decision.tool.name if tool_decision.tool else None,
            score=tool_decision.score,
            reasons=tuple(reasons),
        )

    def select_plan(self, task: Task, steps: tuple[PlanStep, ...]) -> tuple[CapabilityDecision, ...]:
        """Return deterministic capability decisions in plan order; never executes tools."""
        return tuple(self.select(task, step) for step in steps)
