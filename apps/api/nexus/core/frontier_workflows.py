from __future__ import annotations

from dataclasses import dataclass

from .models import ModelRegistry, ModelSpec, model_registry


@dataclass(frozen=True)
class FrontierWorkflowRequest:
    """Explicit model requirements for a frontier-model workflow."""

    required_capabilities: frozenset[str] = frozenset()
    reasoning_level: str = "medium"
    minimum_context_window: int = 0
    require_tools: bool = False

    def __post_init__(self) -> None:
        if self.reasoning_level not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported reasoning level")
        if self.minimum_context_window < 0:
            raise ValueError("minimum_context_window cannot be negative")


@dataclass(frozen=True)
class FrontierWorkflowPlan:
    """Deterministic primary/fallback model sequence with auditable constraints."""

    primary: ModelSpec
    fallbacks: tuple[ModelSpec, ...]
    required_capabilities: frozenset[str]
    reasoning_level: str

    @property
    def candidates(self) -> tuple[ModelSpec, ...]:
        return (self.primary, *self.fallbacks)


class FrontierWorkflowPlanner:
    """Builds a capability-safe model cascade without making execution decisions."""

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self._registry = registry or model_registry

    @staticmethod
    def _supports(spec: ModelSpec, request: FrontierWorkflowRequest) -> bool:
        return (
            request.required_capabilities.issubset(spec.capabilities)
            and request.reasoning_level in spec.reasoning_levels
            and spec.context_window >= request.minimum_context_window
            and (not request.require_tools or spec.supports_tools)
        )

    def plan(self, request: FrontierWorkflowRequest) -> FrontierWorkflowPlan:
        candidates = [spec for spec in self._registry.all() if self._supports(spec, request)]
        if not candidates:
            raise ValueError("no registered model satisfies frontier workflow requirements")
        ordered = sorted(candidates, key=lambda spec: (-spec.context_window, -spec.cost_score, spec.latency_score, spec.key))
        return FrontierWorkflowPlan(
            primary=ordered[0],
            fallbacks=tuple(ordered[1:]),
            required_capabilities=request.required_capabilities,
            reasoning_level=request.reasoning_level,
        )

    def compatible(self, model: ModelSpec, request: FrontierWorkflowRequest) -> bool:
        return self._supports(model, request)
