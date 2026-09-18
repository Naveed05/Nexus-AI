from dataclasses import dataclass, field
from typing import Any, Callable

from nexus.core.agent_orchestrator import AgentAssignment, AgentOrchestrator
from nexus.core.execution_state import ExecutionState, ExecutionStateMachine
from nexus.core.retry_policy import RetryPolicy
from nexus.core.runtime_context import RuntimeContext
from nexus.core.state import AgentState, PlanStep
from nexus.core.task import Task


@dataclass(frozen=True)
class RuntimeResult:
    task_id: str
    state: ExecutionState
    output: Any | None
    error: str | None
    executed_steps: tuple[str, ...]
    transitions: tuple[str, ...]
    attempts: tuple[int, ...] = ()


Stage = Callable[[RuntimeContext, AgentState], Any]


class UnifiedAgentRuntime:
    """Coordinate the NEXUS lifecycle with bounded recovery and context propagation."""

    def __init__(self, *, understand=None, plan=None, route=None, execute=None, observe=None,
                 verify=None, revise=None, deliver=None, orchestrator=None,
                 retry_policy: RetryPolicy | None = None) -> None:
        self._stages = {"understand": understand, "plan": plan, "route": route,
                        "execute": execute, "observe": observe, "verify": verify,
                        "revise": revise, "deliver": deliver}
        self._orchestrator = orchestrator or AgentOrchestrator()
        self._retry_policy = retry_policy or RetryPolicy()

    def run(self, task: Task, state: AgentState | None = None) -> RuntimeResult:
        machine = ExecutionStateMachine()
        agent_state = state or AgentState(task_id=task.task_id, objective=task.objective)
        context = RuntimeContext(task_id=str(task.task_id), objective=task.objective)
        output = None
        executed_steps: list[str] = []
        attempts: list[int] = []
        try:
            self._call("understand", context.for_stage("understand"), agent_state)
            self._call("plan", context.for_stage("plan"), agent_state)
            machine.transition(ExecutionState.PLANNED, reason="execution plan established")
            assignments = self._orchestrator.assign_plan(task, tuple(agent_state.steps))
            context = RuntimeContext(str(task.task_id), task.objective, assignments=(), metadata={}) if False else context
            self._call("route", context.for_stage("route"), agent_state)
            machine.transition(ExecutionState.APPROVED, reason="runtime route established")
            for step in agent_state.steps:
                if step.status.value in {"completed", "skipped"}:
                    continue
                if not agent_state.dependencies_completed(step):
                    raise RuntimeError(f"dependencies not completed for step: {step.step_id}")
                attempt = 0
                while True:
                    attempt += 1
                    step.attempts = attempt
                    try:
                        step_context = context.for_stage("execute", step_id=step.step_id, attempt=attempt)
                        output = self._call("execute", step_context, agent_state, step)
                        executed_steps.append(step.step_id)
                        attempts.append(attempt)
                        self._call("observe", context.for_stage("observe", step_id=step.step_id, attempt=attempt), agent_state, step)
                        break
                    except Exception as exc:
                        if not self._retry_policy.allows(exc, attempt):
                            raise
            machine.transition(ExecutionState.EXECUTING, reason="execution stages completed")
            machine.transition(ExecutionState.VERIFYING, reason="execution output ready for verification")
            verification = self._call("verify", context.for_stage("verify"), agent_state)
            if verification is False or (verification is None and agent_state.steps and not agent_state.completed):
                revised = self._call("revise", context.for_stage("revise"), agent_state)
                if revised is False:
                    raise RuntimeError("runtime verification failed after revision")
            self._call("deliver", context.for_stage("deliver"), agent_state)
            machine.transition(ExecutionState.COMPLETED, reason="verification and delivery completed")
        except Exception as exc:
            if machine.state not in {ExecutionState.COMPLETED, ExecutionState.FAILED}:
                machine.fail(str(exc))
            return self._result(task, machine, output, str(exc), executed_steps, attempts)
        return self._result(task, machine, output, None, executed_steps, attempts)

    @staticmethod
    def _call(name, context, state, step=None):
        callback = self._stages[name]
        if callback is None:
            return None
        return callback(context, state)

    @staticmethod
    def _result(task, machine, output, error, executed_steps, attempts):
        return RuntimeResult(str(task.task_id), machine.state, output, error, tuple(executed_steps),
                             tuple(f"{event.from_state.value}->{event.to_state.value}" for event in machine.history),
                             tuple(attempts))
