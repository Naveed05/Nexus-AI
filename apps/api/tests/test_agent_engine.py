from nexus.core.engine import NexusEngine
from nexus.core.executor import ExecutionResult
from nexus.core.models import model_registry
from nexus.core.state import StepStatus
from nexus.core.task import Task


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[Task] = []

    def execute(self, task: Task, model, allowed_tools=()) -> ExecutionResult:
        self.calls.append(task)
        evidence = ()
        output = "verified-looking test output"
        if task.objective.lower().startswith("research"):
            evidence = (
                {
                    "citation": "research.txt — chunk 1",
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "text": "NEXUS supports grounded research workflows.",
                },
            )
            output = "NEXUS supports grounded research workflows. [Source: research.txt — chunk 1]"
        elif "GROUNDED EVIDENCE" in (task.context or ""):
            output = "NEXUS supports grounded research workflows. [Source: research.txt — chunk 1]"
        return ExecutionResult(
            model_key=model.key,
            model_id=model.model_id,
            response_id=f"resp_{len(self.calls)}",
            output=output,
            tool_calls=(),
            grounded_evidence=evidence,
        )


def test_engine_builds_plan_and_verifies_output() -> None:
    executor = FakeExecutor()
    engine = NexusEngine(executor=executor)
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


def test_engine_carries_retrieved_evidence_into_downstream_steps() -> None:
    executor = FakeExecutor()
    engine = NexusEngine(executor=executor)
    task = Task(objective="Research NEXUS grounding")

    result = engine.run(task)

    assert result.state.verification_passed is True
    syntheses = [call for call in executor.calls if call.objective.lower().startswith("synthesize")]
    assert syntheses
    assert "GROUNDED EVIDENCE" in (syntheses[0].context or "")
    assert "[Source: research.txt — chunk 1]" in (syntheses[0].context or "")
    assert "NEXUS supports grounded research workflows." in (syntheses[0].context or "")
