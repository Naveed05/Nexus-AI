from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import ModelRegistry, ModelSpec, model_registry


class FallbackReason(str, Enum):
    TRANSIENT_FAILURE = "transient_failure"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    CAPABILITY_MISMATCH = "capability_mismatch"


@dataclass(frozen=True)
class FrontierWorkflowRequest:
    """Explicit model requirements and operational budgets for a frontier workflow."""

    required_capabilities: frozenset[str] = frozenset()
    reasoning_level: str = "medium"
    minimum_context_window: int = 0
    require_tools: bool = False
    maximum_cost_score: int | None = None
    maximum_latency_score: int | None = None

    def __post_init__(self) -> None:
        if self.reasoning_level not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported reasoning level")
        if self.minimum_context_window < 0:
            raise ValueError("minimum_context_window cannot be negative")
        if self.maximum_cost_score is not None and self.maximum_cost_score < 0:
            raise ValueError("maximum_cost_score cannot be negative")
        if self.maximum_latency_score is not None and self.maximum_latency_score < 0:
            raise ValueError("maximum_latency_score cannot be negative")


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


@dataclass(frozen=True)
class FallbackDecision:
    """Auditable decision for moving to the next compatible model."""

    should_fallback: bool
    next_model: ModelSpec | None
    reason: FallbackReason


class FrontierWorkflowPlanner:
    """Build a capability-safe model cascade without making execution decisions."""

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self._registry = registry or model_registry

    @staticmethod
    def _supports(spec: ModelSpec, request: FrontierWorkflowRequest) -> bool:
        return (
            request.required_capabilities.issubset(spec.capabilities)
            and request.reasoning_level in spec.reasoning_levels
            and spec.context_window >= request.minimum_context_window
            and (not request.require_tools or spec.supports_tools)
            and (request.maximum_cost_score is None or spec.cost_score <= request.maximum_cost_score)
            and (request.maximum_latency_score is None or spec.latency_score <= request.maximum_latency_score)
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


class FrontierFallbackController:
    """Advances only through prevalidated compatible candidates."""

    @staticmethod
    def decide(
        plan: FrontierWorkflowPlan,
        *,
        current_index: int,
        reason: FallbackReason,
    ) -> FallbackDecision:
        if current_index < 0 or current_index >= len(plan.candidates):
            raise ValueError("current_index is outside the workflow candidate range")
        next_index = current_index + 1
        if next_index >= len(plan.candidates):
            return FallbackDecision(False, None, reason)
        return FallbackDecision(True, plan.candidates[next_index], reason)
