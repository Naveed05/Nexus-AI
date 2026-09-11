from nexus.core.planner import TaskPlanner
from nexus.core.task import Task


def test_data_task_gets_dynamic_execution_graph() -> None:
    steps = TaskPlanner().plan(Task(objective="Analyze this dataset and build a baseline model"))

    assert [step.step_id for step in steps] == [
        "understand",
        "inspect_data",
        "analyze_data",
        "verify",
        "deliver",
    ]
    assert steps[1].depends_on == ("understand",)
    assert steps[2].depends_on == ("inspect_data",)
    assert steps[1].execution_required is True
    assert steps[0].execution_required is False
    assert steps[3].execution_required is False


def test_coding_task_gets_code_execution_graph() -> None:
    steps = TaskPlanner().plan(Task(objective="Debug the repository and fix the failing tests"))

    assert [step.step_id for step in steps] == [
        "understand",
        "inspect_code",
        "implement",
        "verify",
        "deliver",
    ]
    assert steps[2].depends_on == ("inspect_code",)


def test_research_task_gets_research_graph() -> None:
    steps = TaskPlanner().plan(Task(objective="Research the latest approaches and compare sources"))

    assert [step.step_id for step in steps] == [
        "understand",
        "research",
        "synthesize",
        "verify",
        "deliver",
    ]
    assert steps[2].depends_on == ("research",)


def test_general_task_keeps_backward_compatible_shape() -> None:
    steps = TaskPlanner().plan(Task(objective="Write a short summary"))

    assert [step.step_id for step in steps] == ["understand", "execute", "verify", "deliver"]
    assert steps[1].execution_required is True
