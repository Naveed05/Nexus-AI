from uuid import uuid4

import pytest

from nexus.core.runtime import (
    AgentRuntime,
    RunBudget,
    RunBudgetExceededError,
    RunCancelledError,
    RunStatus,
)
from nexus.core.task import Task, TaskStatus


def _task() -> Task:
    return Task(task_id=uuid4(), objective="runtime test")


def test_runtime_tracks_successful_run_and_limits() -> None:
    runtime = AgentRuntime()

    def runner(task, control):
        control.consume_step()
        control.consume_tool_call()
        return {"ok": True}

    run, result = runtime.run(
        _task(),
        runner,
        budget=RunBudget(max_steps=2, max_tool_calls=1),
    )

    assert result == {"ok": True}
    assert run.status == RunStatus.COMPLETED
    assert run.task_status == TaskStatus.COMPLETED
    assert run.steps_completed == 1
    assert run.tool_calls == 1
    assert run.finished_at is not None
    assert run.duration_ms is not None


def test_runtime_enforces_step_budget() -> None:
    runtime = AgentRuntime()

    def runner(task, control):
        control.consume_step()
        control.consume_step()

    with pytest.raises(RunBudgetExceededError):
        runtime.run(_task(), runner, budget=RunBudget(max_steps=1))

    run = runtime.list_runs()[0]
    assert run.status == RunStatus.FAILED
    assert run.task_status == TaskStatus.FAILED
    assert "step budget" in (run.error or "")


def test_runtime_cancellation_is_observable() -> None:
    runtime = AgentRuntime()
    task = _task()
    run = runtime.create_run(task)
    runtime.cancel(run.run_id)

    assert run.status == RunStatus.CANCELLED
    assert run.task_status == TaskStatus.CANCELLED

    with pytest.raises(RunCancelledError):
        runtime.control(run.run_id).check_cancelled()


def test_runtime_mirrors_task_outcome() -> None:
    runtime = AgentRuntime()
    task = _task()

    class Result:
        def __init__(self, task):
            self.task = task

    def runner(current_task, control):
        current_task.status = TaskStatus.FAILED
        return Result(current_task)

    run, _ = runtime.run(task, runner)
    assert run.status == RunStatus.FAILED
    assert run.task_status == TaskStatus.FAILED


def test_runtime_enforces_tool_and_retry_budgets() -> None:
    runtime = AgentRuntime()

    def runner(task, control):
        control.consume_tool_call()
        control.consume_tool_call()

    with pytest.raises(RunBudgetExceededError):
        runtime.run(_task(), runner, budget=RunBudget(max_tool_calls=1))

    def retry_runner(task, control):
        control.consume_retry()
        control.consume_retry()

    with pytest.raises(RunBudgetExceededError):
        runtime.run(_task(), retry_runner, budget=RunBudget(max_retries=1))
