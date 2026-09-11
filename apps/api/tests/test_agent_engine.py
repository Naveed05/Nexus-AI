from nexus.core.engine import NexusEngine
from nexus.core.executor import ExecutionResult
from nexus.core.models import model_registry
from nexus.core.state import StepStatus
from nexus.core.task import Task


class FakeExecutor:
    def execute(self, task: Task, model) -> ExecutionResult:
        return ExecutionResult(
            model_key=model.key,
            model_id=model.model_id,
            response_id="resp_test",
            output="verified-looking test output",
            tool_calls=(),
        )


def test_engine_builds_plan_and_verifies_output() -> None:
    engine = NexusEngine(executor=FakeExecutor())
    task = Task(objective="Analyze the sample dataset")

    result = engine.run(task)

    assert result.model == model_registry.get("terra")
    assert result.state.verification_passed is True
    assert result.state.completed is True
    assert [step.step_id for step in result.state.steps] == [
        "understand",
        "inspect_data",
        "analyze_data",
        "verify",
        "deliver",
    ]
    assert all(
        step.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
        for step in result.state.steps
    )
    event_types = [event.event_type.value for event in result.events]
    assert event_types[0] == "task_started"
    assert "model_routed" in event_types
    assert "plan_created" in event_types
    assert "verification_completed" in event_types
    assert event_types[-1] == "task_completed"

    routed = next(event for event in result.events if event.event_type.value == "model_routed")
    assert routed.data["model_id"] == "gpt-5.6-terra"
    assert routed.data["provider"] == "openai"
    assert routed.data["reasons"]


def test_engine_routes_without_executing() -> None:
    engine = NexusEngine(executor=FakeExecutor())
    task = Task(objective="Debug a complex agent")

    route = engine.route_task(task)

    assert route.model.model_id == "gpt-6-astra"
    assert route.decision.model == route.model
    assert route.decision.score == 95.0
