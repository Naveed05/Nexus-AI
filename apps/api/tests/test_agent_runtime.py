from nexus.core.agent_runtime import UnifiedAgentRuntime
from nexus.core.execution_state import ExecutionState
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
