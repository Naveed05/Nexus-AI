import pytest

from nexus.core.orchestration_checkpoint import OrchestrationCheckpoint
from nexus.core.orchestrator import OrchestratorState, TaskDecomposer
from nexus.core.resume_controller import ResumeController
from nexus.core.state import StepStatus
from nexus.core.task import Task


def test_resume_restores_ready_state_from_checkpoint(tmp_path) -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    state.start_step("understand")
    state.fail_step("understand", "temporary")
    state.plan.step_by_id("understand").status = StepStatus.PENDING
    state.plan.step_by_id("understand").error = None
    state.status = "ready"

    path = OrchestrationCheckpoint().save(state, tmp_path / "resume.json")
    restored = ResumeController().resume(path)

    assert restored.status == "ready"
    assert restored.current_step_id is None
    assert restored.ready_steps()[0].step_id == "understand"
    assert restored.plan.step_by_id("understand").attempts == 1


def test_resume_rejects_running_checkpoint(tmp_path) -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    state.start_step("understand")
    path = OrchestrationCheckpoint().save(state, tmp_path / "running.json")

    with pytest.raises(ValueError, match="running steps"):
        ResumeController().resume(path)


def test_resume_preserves_failed_state_for_explicit_recovery(tmp_path) -> None:
    task = Task(objective="Write a summary")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    state.start_step("understand")
    state.fail_step("understand", "blocked")
    path = OrchestrationCheckpoint().save(state, tmp_path / "failed.json")

    restored = ResumeController().resume(path)

    assert restored.status == "failed"
    assert restored.current_step_id is None
    assert restored.plan.step_by_id("understand").status == StepStatus.FAILED
