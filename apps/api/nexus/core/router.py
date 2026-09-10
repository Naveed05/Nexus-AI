from dataclasses import dataclass

from nexus.core.models import ModelSpec, model_registry
from nexus.core.task import RiskLevel, Task


@dataclass(frozen=True)
class RoutingDecision:
    """Observable routing metadata; never contains hidden model reasoning."""

    model: ModelSpec
    score: float
    reasons: tuple[str, ...]


class TaskRouter:
    """Deterministic, explainable first-pass model routing for NEXUS."""

    _hard_signals = (
        "architecture",
        "debug",
        "debugging",
        "research",
        "complex",
        "reason",
        "agent",
        "multi-step",
        "design system",
    )
    _professional_capabilities = {
        "data_analysis",
        "machine_learning",
        "coding",
        "document_analysis",
        "research",
    }

    def decide(self, task: Task) -> RoutingDecision:
        objective = task.objective.lower()
        reasons: list[str] = []

        if task.risk_level == RiskLevel.HIGH:
            reasons.append("high-risk task requires the strongest available reasoning model")
            return RoutingDecision(model_registry.get("astra"), 100.0, tuple(reasons))

        if any(signal in objective for signal in self._hard_signals):
            reasons.append("objective contains a high-complexity signal")
            return RoutingDecision(model_registry.get("astra"), 95.0, tuple(reasons))

        if task.capabilities and self._professional_capabilities.intersection(task.capabilities):
            reasons.append("task requests professional-domain capabilities")
            if task.budget is None or task.budget > 1:
                return RoutingDecision(model_registry.get("sol"), 80.0, tuple(reasons))

        if task.budget is not None and task.budget <= 1:
            reasons.append("task budget is constrained")
            return RoutingDecision(model_registry.get("luna"), 60.0, tuple(reasons))

        reasons.append("general task uses the balanced default model")
        return RoutingDecision(model_registry.get("terra"), 50.0, tuple(reasons))

    def route(self, task: Task) -> ModelSpec:
        """Backward-compatible shorthand returning only the selected model."""
        return self.decide(task).model


router = TaskRouter()
