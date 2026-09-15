import pytest

from nexus.core.orchestrator import OrchestratorState, TaskDecomposer, TaskPlan
from nexus.core.state import PlanStep, StepStatus
from nexus.core.task import Task


def test_decomposer_builds_valid_dependency_aware_plan() -> None:
    task = Task(objective="Debug the repository and fix the failing tests")
    plan = TaskDecomposer().decompose(task)

    assert plan.task_id == task.task_id
    assert plan.objective == task.objective
    assert [step.step_id for step in plan.steps] == [
        "understand",
        "inspect_code",
        "implement",
        "verify",
        "deliver",
    ]
    assert [step.step_id for step in plan.ready_steps()] == ["understand"]


def test_orchestrator_state_enforces_dependencies_and_transitions() -> None:
    plan = TaskDecomposer().decompose(Task(objective="Write a short summary"))
    state = OrchestratorState(plan=plan)

    with pytest.raises(ValueError, match="not ready"):
        state.start_step("execute")

    state.start_step("understand")
    assert plan.step_by_id("understand").status == StepStatus.RUNNING
    state.complete_step("understand", "understood")
    assert [step.step_id for step in state.ready_steps()] == ["execute"]

    state.start_step("execute")
    state.complete_step("execute", "result")
    assert [step.step_id for step in state.ready_steps()] == ["verify"]
    assert state.history == [
        "started:understand",
        "completed:understand",
        "started:execute",
        "completed:execute",
    ]


def test_task_plan_rejects_unknown_dependencies_and_cycles() -> None:
    with pytest.raises(ValueError, match="unknown dependencies"):
        TaskPlan(
            task_id=Task(objective="test").task_id,
            objective="test",
            steps=(PlanStep("a", "A", depends_on=("missing",)),),
        )

    a = PlanStep("a", "A", depends_on=("b",))
    b = PlanStep("b", "B", depends_on=("a",))
    with pytest.raises(ValueError, match="acyclic"):
        TaskPlan(task_id=Task(objective="test").task_id, objective="test", steps=(a, b))


def test_failed_step_moves_orchestrator_to_failed_state() -> None:
    plan = TaskDecomposer().decompose(Task(objective="Write a short summary"))
    state = OrchestratorState(plan=plan)
    state.start_step("understand")
    state.fail_step("understand", "temporary failure")

    assert state.status == "failed"
    assert state.current_step_id is None
    assert plan.step_by_id("understand").status == StepStatus.FAILED
    assert plan.step_by_id("understand").error == "temporary failure"
