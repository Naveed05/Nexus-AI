import pytest

from nexus.core.execution_loop import OrchestrationExecutor
from nexus.core.orchestrator import OrchestratorState, TaskDecomposer
from nexus.core.task import Task


def test_execution_loop_runs_only_ready_step_and_requires_verification() -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    calls: list[str] = []

    result = OrchestrationExecutor().execute_next(
        task,
        state,
        executor=lambda decision: calls.append(decision.step_id) or "context",
        verifier=lambda value: value == "context",
    )

    assert result is not None
    assert result.verification is not None
    assert result.verification.passed is True
    assert calls == ["understand"]
    assert state.plan.step_by_id("understand").attempts == 1
    assert state.plan.step_by_id("understand").status.value == "completed"
    assert state.ready_steps()[0].step_id == "research"


def test_failed_verification_blocks_progression() -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))

    result = OrchestrationExecutor().execute_next(
        task,
        state,
        executor=lambda decision: "bad result",
        verifier=lambda value: False,
    )

    assert result is not None
    assert result.verification is not None
    assert result.verification.passed is False
    assert state.plan.step_by_id("understand").status.value == "failed"
    assert state.ready_steps() == ()


def test_execution_failure_is_recorded_without_verification() -> None:
    task = Task(objective="Write a summary")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))

    result = OrchestrationExecutor().execute_next(
        task,
        state,
        executor=lambda decision: (_ for _ in ()).throw(RuntimeError("boom")),
        verifier=lambda value: True,
    )

    assert result is not None
    assert result.error == "boom"
    assert result.verification is None
    assert state.plan.step_by_id("understand").status.value == "failed"


def test_execute_next_returns_none_when_no_step_is_ready() -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    state.start_step("understand")
    state.fail_step("understand", "blocked")

    assert OrchestrationExecutor().execute_next(
        task,
        state,
        executor=lambda decision: "unused",
        verifier=lambda value: True,
    ) is None
