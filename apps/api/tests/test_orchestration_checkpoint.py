from pathlib import Path

from nexus.core.orchestration_checkpoint import OrchestrationCheckpoint
from nexus.core.orchestrator import OrchestratorState, TaskDecomposer
from nexus.core.state import StepStatus
from nexus.core.task import Task


def test_checkpoint_round_trip_preserves_orchestration_state(tmp_path: Path) -> None:
    task = Task(objective="Research a topic")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    state.start_step("understand")
    state.plan.step_by_id("understand").attempts = 2
    state.plan.step_by_id("understand").selected_tool = "memory"
    state.plan.step_by_id("understand").tool_score = 0.75
    state.plan.step_by_id("understand").observation = {"source": "memory"}
    state.fail_step("understand", "temporary failure")
    state.history.append("checkpoint:test")

    path = OrchestrationCheckpoint().save(state, tmp_path / "orchestration.json")
    restored = OrchestrationCheckpoint().load(path)

    assert restored.plan.task_id == state.plan.task_id
    assert restored.plan.objective == state.plan.objective
    assert restored.status == state.status
    assert restored.current_step_id == state.current_step_id
    assert restored.history == state.history

    step = restored.plan.step_by_id("understand")
    assert step.status == StepStatus.FAILED
    assert step.attempts == 2
    assert step.selected_tool == "memory"
    assert step.tool_score == 0.75
    assert step.observation == {"source": "memory"}
    assert step.error == "temporary failure"


def test_checkpoint_creates_parent_directory(tmp_path: Path) -> None:
    task = Task(objective="Write a summary")
    state = OrchestratorState(plan=TaskDecomposer().decompose(task))
    target = tmp_path / "nested" / "state.json"

    saved = OrchestrationCheckpoint().save(state, target)

    assert saved == target
    assert target.exists()
    assert OrchestrationCheckpoint().load(target).plan.objective == "Write a summary"
