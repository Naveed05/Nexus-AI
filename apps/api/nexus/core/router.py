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
        requested_reasoning = self._requested_reasoning(task)
        required_capabilities = set(task.capabilities)
        needs_tools = "tools" in required_capabilities or "agentic" in required_capabilities
        estimated_input_tokens = self._estimate_input_tokens(task)

        compatible = model_registry.find(
            required_capabilities=required_capabilities,
            reasoning_level=requested_reasoning,
            estimated_input_tokens=estimated_input_tokens,
            needs_tools=needs_tools,
        )
        if compatible:
            # Preserve the existing high-signal behavior when its preferred
            # model is compatible, while using model contracts as a hard gate.
            preferred_key = "astra" if task.risk_level == RiskLevel.HIGH or any(signal in objective for signal in self._hard_signals) else None
            if preferred_key:
                preferred = model_registry.get(preferred_key)
                fits, score, fit_reasons = preferred.fit_score(
                    required_capabilities=required_capabilities,
                    reasoning_level=requested_reasoning,
                    estimated_input_tokens=estimated_input_tokens,
                    needs_tools=needs_tools,
                )
                if fits:
                    reasons.extend(fit_reasons)
                    reasons.append("highest-priority reasoning model compatible with task requirements")
                    return RoutingDecision(preferred, 100.0, tuple(reasons))
            selected = compatible[0]
            _, _, fit_reasons = selected.fit_score(
                required_capabilities=required_capabilities,
                reasoning_level=requested_reasoning,
                estimated_input_tokens=estimated_input_tokens,
                needs_tools=needs_tools,
            )
            reasons.extend(fit_reasons)
            reasons.append("selected from models compatible with capability, reasoning, tool, and context constraints")
            return RoutingDecision(selected, 75.0, tuple(reasons))

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

    @staticmethod
    def _estimate_input_tokens(task: Task) -> int:
        text = " ".join(part for part in (task.objective, task.context or "", *task.constraints) if part)
        return max(1, len(text) // 4)

    @staticmethod
    def _requested_reasoning(task: Task) -> str | None:
        for capability in task.capabilities:
            value = capability.strip().lower()
            if value.startswith("reasoning:"):
                return value.split(":", 1)[1].strip()
        return None

    def route(self, task: Task) -> ModelSpec:
        """Backward-compatible shorthand returning only the selected model."""
        return self.decide(task).model


router = TaskRouter()
