import pytest

from nexus.core.execution_coordinator import ExecutionCoordinator
from nexus.core.orchestrator import OrchestratorState, TaskDecomposer
from nexus.core.recovery import RecoveryPolicy
from nexus.core.state import StepStatus
from nexus.core.task import Task


def test_execution_coordinator_prepares_only_ready_step() -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    coordinator = ExecutionCoordinator()

    with pytest.raises(ValueError, match="not ready"):
        coordinator.prepare(task, state, "research")

    decision = coordinator.prepare(task, state, "understand")
    assert decision.step_id == "understand"
    assert decision.agent.agent == "memory"
    assert decision.capability.capability == "context_understanding"
    assert state.plan.step_by_id("understand").selected_tool is None


def test_execution_coordinator_records_safe_tool_selection() -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    state.start_step("understand")
    state.complete_step("understand", "context")

    decision = ExecutionCoordinator().prepare(task, state, "research")
    assert decision.agent.agent == "research"
    assert decision.capability.capability == "research"
    assert decision.capability.tool in {"research_knowledge", "search_knowledge", None}
    assert state.plan.step_by_id("research").selected_tool == decision.capability.tool


def test_recovery_policy_is_bounded_and_deterministic() -> None:
    task = Task(objective="Write a summary")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    state.start_step("understand")
    state.fail_step("understand", "temporary failure")
    step = state.plan.step_by_id("understand")

    policy = RecoveryPolicy(max_attempts=2)
    retry = policy.decide(step)
    assert retry.action == "retry"
    assert retry.next_attempt == 1

    step.attempts = 2
    halt = policy.decide(step)
    assert halt.action == "halt"
    assert halt.next_attempt == 3


def test_recovery_policy_rejects_non_failed_steps() -> None:
    task = Task(objective="Write a summary")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    step = state.plan.step_by_id("understand")

    with pytest.raises(ValueError, match="failed steps"):
        RecoveryPolicy().decide(step)
