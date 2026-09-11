from nexus.core.engine import NexusEngine
from nexus.core.executor import ExecutionResult
from nexus.core.models import model_registry
from nexus.core.task import Task


class RecordingExecutor:
    def __init__(self) -> None:
        self.objectives: list[str] = []

    def execute(self, task: Task, model) -> ExecutionResult:
        self.objectives.append(task.objective)
        return ExecutionResult(
            model_key=model.key,
            model_id=model.model_id,
            response_id=f"resp_{len(self.objectives)}",
            output=f"completed: {task.objective}",
            tool_calls=(),
        )


def test_engine_executes_each_dynamic_data_step_in_dependency_order() -> None:
    executor = RecordingExecutor()
    engine = NexusEngine(executor=executor)
    task = Task(objective="Analyze the dataset and explain the main findings")

    result = engine.run(task)

    assert result.model == model_registry.get("terra")
    assert executor.objectives == [
        "Inspect the dataset structure, schema, missingness, and basic quality.",
        "Analyze the dataset and explain the main findings",
    ]
    assert [step.status.value for step in result.state.steps] == [
        "completed",
        "completed",
        "completed",
        "completed",
        "completed",
    ]
    assert result.state.metadata["plan_type"] == "data"
    assert result.state.completed is True

    step_events = [
        event.data["step_id"]
        for event in result.events
        if event.event_type.value == "step_started"
    ]
    assert step_events == ["inspect_data", "analyze_data"]
