import pytest

from nexus.core.engine import NexusEngine, RetryPolicy
from nexus.core.executor import ExecutionResult
from nexus.core.models import model_registry
from nexus.core.task import Task


class FailOnceExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, task: Task, model) -> ExecutionResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient provider failure")
        return ExecutionResult(
            model_key=model.key,
            model_id=model.model_id,
            response_id="resp_recovered",
            output="recovered output",
            tool_calls=(),
        )


class AlwaysFailExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, task: Task, model) -> ExecutionResult:
        self.calls += 1
        raise RuntimeError("persistent failure")


def test_retry_policy_rejects_invalid_attempt_count() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


def test_engine_recovers_from_transient_execution_failure() -> None:
    executor = FailOnceExecutor()
    engine = NexusEngine(executor=executor, retry_policy=RetryPolicy(max_attempts=2))
    task = Task(objective="Write a short summary")

    result = engine.run(task)

    assert executor.calls == 2
    execute_step = next(step for step in result.state.steps if step.step_id == "execute")
    assert execute_step.attempts == 2
    assert execute_step.status.value == "completed"
    event_types = [event.event_type.value for event in result.events]
    assert "step_failed" in event_types
    assert "retry_scheduled" in event_types
    assert "execution_recovered" in event_types
    assert event_types[-1] == "task_completed"
    assert result.model == model_registry.get("terra")


def test_engine_stops_after_retry_budget_is_exhausted() -> None:
    executor = AlwaysFailExecutor()
    engine = NexusEngine(executor=executor, retry_policy=RetryPolicy(max_attempts=2))
    task = Task(objective="Write a short summary")

    with pytest.raises(RuntimeError, match="persistent failure"):
        engine.run(task)

    assert executor.calls == 2
