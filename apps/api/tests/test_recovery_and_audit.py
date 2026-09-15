from nexus.core.orchestration_audit import OrchestrationAudit
from nexus.core.orchestrator import OrchestratorState, TaskDecomposer
from nexus.core.recovery import RecoveryPolicy
from nexus.core.recovery_controller import RecoveryController
from nexus.core.state import StepStatus
from nexus.core.task import Task


def test_recovery_controller_requeues_failed_step_within_budget() -> None:
    state = OrchestratorState(plan=TaskDecomposer().decompose(Task(objective="Write a summary")))
    state.start_step("understand")
    state.fail_step("understand", "temporary failure")

    decision = RecoveryController(RecoveryPolicy(max_attempts=2)).recover(state, "understand")

    assert decision.action == "retry"
    assert state.plan.step_by_id("understand").status == StepStatus.PENDING
    assert state.plan.step_by_id("understand").error is None
    assert state.status == "ready"
    assert state.history[-1] == "retry:understand:attempt:1"


def test_recovery_controller_halts_after_budget_exhaustion() -> None:
    state = OrchestratorState(plan=TaskDecomposer().decompose(Task(objective="Write a summary")))
    state.start_step("understand")
    state.fail_step("understand", "failure")
    step = state.plan.step_by_id("understand")
    step.attempts = 2

    decision = RecoveryController(RecoveryPolicy(max_attempts=2)).recover(state, "understand")

    assert decision.action == "halt"
    assert step.status == StepStatus.FAILED
    assert state.status == "failed"
    assert state.history[-1] == "halt:understand:attempt:3"


def test_orchestration_audit_records_immutable_ordered_events() -> None:
    audit = OrchestrationAudit()
    first = audit.record("started", "understand", attempt=1, agent="memory")
    second = audit.record("completed", "understand", result="context")

    events = audit.events()
    assert events == (first, second)
    assert first.details == {"agent": "memory", "attempt": 1}
    assert first.timestamp.endswith("+00:00")

    audit.clear()
    assert audit.events() == ()
