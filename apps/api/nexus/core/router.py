from dataclasses import dataclass

from nexus.core.models import ModelRequirements, ModelSpec, model_registry
from nexus.core.task import RiskLevel, Task


@dataclass(frozen=True)
class ModelSelectionScore:
    """Explainable score components used to rank eligible models."""

    model: ModelSpec
    total: float
    capability_fit: float
    reasoning_fit: float
    context_fit: float
    cost_fit: float
    latency_fit: float


@dataclass(frozen=True)
class RoutingDecision:
    """Observable routing metadata; never contains hidden model reasoning."""

    model: ModelSpec
    score: float
    reasons: tuple[str, ...]
    candidates: tuple[ModelSelectionScore, ...] = ()


class TaskRouter:
    """Deterministic, explainable multi-factor model routing for NEXUS."""

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
    _tier_rank = {"economy": 1, "balanced": 2, "professional": 3, "flagship": 4}

    def _requirements(self, task: Task, *, hard: bool) -> ModelRequirements:
        reasoning_level = "max" if task.risk_level == RiskLevel.HIGH else "high" if hard else None
        return ModelRequirements(
            reasoning_level=reasoning_level,
            require_tools=True,
            maximum_cost_score=1 if task.budget is not None and task.budget <= 1 else None,
        )

    def _eligible_models(self, task: Task, *, hard: bool, professional: bool, provider: str | None = None) -> tuple[ModelSpec, ...]:
        requirements = self._requirements(task, hard=hard)
        models = model_registry.find(requirements)
        if provider:
            models = tuple(model for model in models if model.provider == provider.strip().lower())
        if professional and not (task.budget is not None and task.budget <= 1):
            models = tuple(
                model for model in models if self._tier_rank[model.tier] >= self._tier_rank["professional"]
            )
        if hard and task.risk_level != RiskLevel.HIGH:
            models = tuple(model for model in models if model.reasoning_levels & {"high", "xhigh", "max"})
        return models

    def _score(self, model: ModelSpec, task: Task, *, hard: bool, professional: bool) -> ModelSelectionScore:
        requested = set(task.capabilities)
        known_requested = requested.intersection(model.capabilities)
        capability_fit = 1.0 if not requested else len(known_requested) / max(1, len(requested))
        reasoning_fit = 1.0 if hard and "high" in model.reasoning_levels else 0.75 if not hard else 0.0
        context_fit = min(1.0, model.context_window / 200_000)
        cost_fit = 1.0 - (model.cost_score - 1) / 4
        latency_fit = 1.0 - (model.latency_score - 2) / 3
        tier_bonus = 0.10 if professional and model.tier == "professional" else 0.0
        total = (
            capability_fit * 0.35
            + reasoning_fit * 0.25
            + context_fit * 0.10
            + cost_fit * 0.15
            + latency_fit * 0.15
            + tier_bonus
        )
        return ModelSelectionScore(model, round(total, 4), round(capability_fit, 4), round(reasoning_fit, 4), round(context_fit, 4), round(cost_fit, 4), round(latency_fit, 4))

    def decide(self, task: Task, provider: str | None = None) -> RoutingDecision:
        objective = task.objective.lower()
        hard = any(signal in objective for signal in self._hard_signals)
        professional = bool(task.capabilities and self._professional_capabilities.intersection(task.capabilities))
        reasons: list[str] = []

        if task.risk_level == RiskLevel.HIGH:
            reasons.append("high-risk task requires the strongest available reasoning model")
            eligible = self._eligible_models(task, hard=True, professional=False, provider=provider)
            selected = model_registry.get("astra")
            score = 100.0
        elif hard:
            reasons.append("objective contains a high-complexity signal")
            eligible = self._eligible_models(task, hard=True, professional=False, provider=provider)
            selected = model_registry.get("astra")
            score = 95.0
        elif professional and not (task.budget is not None and task.budget <= 1):
            reasons.append("task requests professional-domain capabilities")
            eligible = self._eligible_models(task, hard=False, professional=True, provider=provider)
            selected = model_registry.get("sol") if any(model.key == "sol" for model in eligible) else eligible[0]
            score = 80.0
        elif task.budget is not None and task.budget <= 1:
            reasons.append("task budget is constrained")
            eligible = self._eligible_models(task, hard=False, professional=False, provider=provider)
            selected = model_registry.get("luna")
            score = 60.0
        else:
            reasons.append("general task uses the balanced default model")
            eligible = self._eligible_models(task, hard=False, professional=False, provider=provider)
            selected = model_registry.get("terra")
            score = 50.0

        if provider and (selected.provider != provider.strip().lower() or selected not in eligible):
            if not eligible:
                raise ValueError(f"no {provider} model satisfies the task requirements")
            selected = eligible[0]

        if selected not in eligible:
            eligible = tuple(dict.fromkeys((*eligible, selected)))
        candidates = tuple(sorted((self._score(model, task, hard=hard, professional=professional) for model in eligible), key=lambda item: (-item.total, item.model.cost_score, item.model.key)))
        reasons.append(f"selected {selected.key} using capability, reasoning, context, cost, and latency factors")
        return RoutingDecision(selected, score, tuple(reasons), candidates)

    def route(self, task: Task, provider: str | None = None) -> ModelSpec:
        """Backward-compatible shorthand returning only the selected model."""
        return self.decide(task, provider=provider).model


router = TaskRouter()
