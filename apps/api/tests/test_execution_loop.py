import pytest

from nexus.core.execution_loop import OrchestrationExecutor
from nexus.core.orchestration_audit import OrchestrationAudit
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


def test_execution_audit_records_successful_lifecycle() -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    audit = OrchestrationAudit()

    result = OrchestrationExecutor(audit=audit).execute_next(
        task,
        state,
        executor=lambda decision: "context",
        verifier=lambda value: True,
    )

    assert result is not None
    assert [event.event for event in audit.events()] == [
        "started",
        "executed",
        "verified",
        "completed",
    ]
    assert audit.events()[0].details["agent"] == "memory"


def test_recovery_audit_records_retry_and_halt() -> None:
    from nexus.core.recovery import RecoveryPolicy
    from nexus.core.recovery_controller import RecoveryController

    task = Task(objective="Write a summary")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    audit = OrchestrationAudit()
    controller = RecoveryController(RecoveryPolicy(max_attempts=1), audit=audit)

    state.start_step("understand")
    state.fail_step("understand", "temporary")
    controller.recover(state, "understand")

    state.start_step("understand")
    state.fail_step("understand", "again")
    controller.recover(state, "understand")

    assert [event.event for event in audit.events()] == ["retry", "halt"]
    assert audit.events()[0].details["attempt"] == 1
    assert audit.events()[1].details["attempt"] == 2
