import pytest

from nexus.core.frontier_workflows import (
    FallbackReason,
    FrontierFallbackController,
    FrontierWorkflowPlanner,
    FrontierWorkflowRequest,
)


def test_frontier_planner_selects_only_capability_compatible_models() -> None:
    planner = FrontierWorkflowPlanner()
    request = FrontierWorkflowRequest(
        required_capabilities=frozenset({"multimodal", "agentic"}),
        reasoning_level="high",
        minimum_context_window=100_000,
        require_tools=True,
    )
    plan = planner.plan(request)
    assert plan.primary.key == "astra"
    assert all(planner.compatible(model, request) for model in plan.candidates)
    assert all("multimodal" in model.capabilities for model in plan.candidates)


def test_frontier_planner_rejects_impossible_requirements() -> None:
    planner = FrontierWorkflowPlanner()
    request = FrontierWorkflowRequest(
        required_capabilities=frozenset({"nonexistent-capability"}),
        reasoning_level="high",
    )
    with pytest.raises(ValueError, match="no registered model"):
        planner.plan(request)


def test_frontier_request_validates_reasoning_and_context() -> None:
    with pytest.raises(ValueError, match="reasoning"):
        FrontierWorkflowRequest(reasoning_level="extreme")
    with pytest.raises(ValueError, match="context"):
        FrontierWorkflowRequest(minimum_context_window=-1)


def test_frontier_fallback_controller_advances_in_order() -> None:
    plan = FrontierWorkflowPlanner().plan(
        FrontierWorkflowRequest(required_capabilities=frozenset({"reasoning"}), reasoning_level="medium")
    )
    decision = FrontierFallbackController.decide(
        plan,
        current_index=0,
        reason=FallbackReason.TRANSIENT_FAILURE,
    )
    assert decision.should_fallback
    assert decision.next_model == plan.candidates[1]
    assert decision.reason is FallbackReason.TRANSIENT_FAILURE


def test_frontier_fallback_controller_stops_at_last_candidate() -> None:
    plan = FrontierWorkflowPlanner().plan(FrontierWorkflowRequest(reasoning_level="max"))
    decision = FrontierFallbackController.decide(
        plan,
        current_index=len(plan.candidates) - 1,
        reason=FallbackReason.PROVIDER_ERROR,
    )
    assert not decision.should_fallback
    assert decision.next_model is None


def test_frontier_fallback_controller_rejects_invalid_index() -> None:
    plan = FrontierWorkflowPlanner().plan(FrontierWorkflowRequest())
    with pytest.raises(ValueError, match="current_index"):
        FrontierFallbackController.decide(plan, current_index=-1, reason=FallbackReason.TIMEOUT)
