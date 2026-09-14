from nexus.core.engine import NexusEngine
from nexus.core.executor import ExecutionResult
from nexus.core.memory import MemoryStore
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


def test_engine_emits_verification_telemetry() -> None:
    executor = FakeExecutor()
    engine = NexusEngine(executor=executor)
    result = engine.run(Task(objective="Research NEXUS grounding"))

    verification_event = next(
        event for event in result.events
        if event.event_type.value == "verification_completed"
    )
    assert verification_event.data["passed"] is True
    assert verification_event.data["grounding_count"] == 1
    assert verification_event.data["grounded_evidence_count"] == 1
    assert verification_event.data["grounding_score"] > 0

    verification_step = next(step for step in result.state.steps if step.step_id == "verify")
    assert verification_step.observation["grounding_count"] == 1
    assert verification_step.observation["grounding_score"] > 0


def test_engine_recalls_and_captures_verified_workspace_memory() -> None:
    memory = MemoryStore()
    workspace_id = Task(objective="Analyze the sample dataset").workspace_id
    assert workspace_id is None

    first_executor = FakeExecutor()
    first_engine = NexusEngine(executor=first_executor, memory=memory)
    first_engine.run(Task(objective="Analyze the sample dataset"))

    records = memory.list(workspace_id=None)
    assert len(records) == 1
    assert "Verified outcome:" in records[0].content
    assert "verified" in records[0].tags

    second_executor = FakeExecutor()
    second_engine = NexusEngine(executor=second_executor, memory=memory)
    second_engine.run(Task(objective="Analyze the sample dataset"))

    assert second_executor.calls
    assert "RECALLED MEMORY (workspace-scoped):" in (second_executor.calls[0].context or "")
    assert "Verified outcome:" in (second_executor.calls[0].context or "")
