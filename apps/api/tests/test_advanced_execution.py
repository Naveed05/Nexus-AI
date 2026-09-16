import pytest

from nexus.core.advanced_execution import AdaptiveReplanner, ExecutionBudget, ReplanTrigger


def test_execution_budget_enforces_hard_limits() -> None:
    budget = ExecutionBudget(max_steps=3, max_attempts=4, max_replans=2)
    assert budget.can_start_step(0)
    assert budget.can_start_step(2)
    assert not budget.can_start_step(3)
    assert budget.can_attempt(3)
    assert not budget.can_attempt(4)
    assert budget.can_replan(1)
    assert not budget.can_replan(2)


def test_execution_budget_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="max_steps"):
        ExecutionBudget(max_steps=0)
    with pytest.raises(ValueError, match="max_attempts"):
        ExecutionBudget(max_attempts=0)
    with pytest.raises(ValueError, match="max_replans"):
        ExecutionBudget(max_replans=-1)


def test_replanner_prioritizes_dependency_failures() -> None:
    decision = AdaptiveReplanner.decide(
        verification_passed=False,
        execution_failed=True,
        dependency_failed=True,
        replans_used=0,
    )
    assert decision.should_replan
    assert decision.trigger is ReplanTrigger.DEPENDENCY_FAILED
    assert decision.replan_index == 1


def test_replanner_handles_execution_and_verification_failures() -> None:
    execution = AdaptiveReplanner.decide(verification_passed=False, execution_failed=True)
    verification = AdaptiveReplanner.decide(verification_passed=False)
    assert execution.trigger is ReplanTrigger.EXECUTION_FAILED
    assert verification.trigger is ReplanTrigger.VERIFICATION_FAILED
    assert execution.should_replan and verification.should_replan


def test_replanner_stops_after_success_or_budget_exhaustion() -> None:
    success = AdaptiveReplanner.decide(verification_passed=True, replans_used=0)
    exhausted = AdaptiveReplanner.decide(
        verification_passed=False,
        replans_used=2,
        budget=ExecutionBudget(max_replans=2),
    )
    assert not success.should_replan
    assert not exhausted.should_replan
    assert exhausted.replan_index == 2
