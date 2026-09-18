from nexus.core.agent_runtime import UnifiedAgentRuntime
from nexus.core.execution_state import ExecutionState
from nexus.core.retry_policy import RetryPolicy
from nexus.core.state import AgentState, PlanStep, StepStatus
from nexus.core.task import Task


def test_unified_runtime_connects_lifecycle():
    task = Task(objective="complete a test workflow")
    state = AgentState(
        task_id=task.task_id,
        objective=task.objective,
        steps=[PlanStep(step_id="research", objective="research")],
    )

    def plan(_context, agent_state):
        agent_state.steps[0].status = StepStatus.COMPLETED

    runtime = UnifiedAgentRuntime(plan=plan)
    result = runtime.run(task, state)

    assert result.state is ExecutionState.COMPLETED
    assert result.error is None
    assert result.transitions == (
        "created->planned",
        "planned->approved",
        "approved->executing",
        "executing->verifying",
        "verifying->completed",
    )


def test_unified_runtime_fails_closed_on_stage_error():
    task = Task(objective="fail safely")

    def understand(_context, _state):
        raise RuntimeError("stage failed")

    result = UnifiedAgentRuntime(understand=understand).run(task)

    assert result.state is ExecutionState.FAILED
    assert result.error == "stage failed"
    assert result.transitions == ("created->failed",)


def test_runtime_retries_transient_step_failure():
    task = Task(objective="retry transient work")
    state = AgentState(task_id=task.task_id, objective=task.objective, steps=[PlanStep(step_id="work", objective="work")])
    calls = {"count": 0}
    def execute(_context, _state):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("temporary")
        return "done"
    result = UnifiedAgentRuntime(execute=execute, retry_policy=RetryPolicy(max_attempts=2)).run(task, state)
    assert result.state is ExecutionState.COMPLETED
    assert result.error is None
    assert calls["count"] == 2
    assert result.attempts == (2,)


def test_runtime_does_not_retry_non_transient_failure():
    task = Task(objective="do not retry")
    state = AgentState(task_id=task.task_id, objective=task.objective, steps=[PlanStep(step_id="work", objective="work")])
    calls = {"count": 0}
    def execute(_context, _state):
        calls["count"] += 1
        raise ValueError("permanent")
    result = UnifiedAgentRuntime(execute=execute, retry_policy=RetryPolicy(max_attempts=3)).run(task, state)
    assert result.state is ExecutionState.FAILED
    assert calls["count"] == 1


def test_runtime_propagates_stage_and_step_context():
    task = Task(objective="inspect context")
    state = AgentState(task_id=task.task_id, objective=task.objective, steps=[PlanStep(step_id="work", objective="work")])
    seen = []
    def execute(context, _state):
        seen.append((context.stage, context.task_id, context.objective, context.step_id, context.attempt, context.assignments))
        return "done"
    result = UnifiedAgentRuntime(execute=execute).run(task, state)
    assert result.state is ExecutionState.COMPLETED
    assert seen == [("execute", str(task.task_id), task.objective, "work", 1, ())]
