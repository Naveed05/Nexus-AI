from dataclasses import dataclass, field
from typing import Any, Callable

from nexus.core.agent_orchestrator import AgentAssignment, AgentOrchestrator
from nexus.core.execution_state import ExecutionState, ExecutionStateMachine
from nexus.core.state import AgentState, PlanStep
from nexus.core.task import Task


@dataclass(frozen=True)
class RuntimeContext:
    """Immutable context shared by every stage of one agent execution."""

    task: Task
    assignments: tuple[AgentAssignment, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeResult:
    """Stable result envelope returned by the unified runtime."""

    task_id: str
    state: ExecutionState
    output: Any | None
    error: str | None
    executed_steps: tuple[str, ...]
    transitions: tuple[str, ...]


Stage = Callable[[RuntimeContext, AgentState], Any]


class UnifiedAgentRuntime:
    """Coordinate the NEXUS execution lifecycle through explicit stage boundaries."""

    def __init__(
        self,
        *,
        understand: Stage | None = None,
        plan: Stage | None = None,
        route: Stage | None = None,
        execute: Stage | None = None,
        observe: Stage | None = None,
        verify: Stage | None = None,
        revise: Stage | None = None,
        deliver: Stage | None = None,
        orchestrator: AgentOrchestrator | None = None,
    ) -> None:
        self._stages = {
            "understand": understand,
            "plan": plan,
            "route": route,
            "execute": execute,
            "observe": observe,
            "verify": verify,
            "revise": revise,
            "deliver": deliver,
        }
        self._orchestrator = orchestrator or AgentOrchestrator()

    def run(self, task: Task, state: AgentState | None = None) -> RuntimeResult:
        machine = ExecutionStateMachine()
        agent_state = state or AgentState(task_id=task.task_id, objective=task.objective)
        context = RuntimeContext(task=task)
        output: Any | None = None
        executed_steps: list[str] = []

        try:
            self._call("understand", context, agent_state)
            self._call("plan", context, agent_state)
            machine.transition(ExecutionState.PLANNED, reason="execution plan established")

            assignments = self._orchestrator.assign_plan(task, tuple(agent_state.steps))
            context = RuntimeContext(task=task, assignments=assignments, metadata=context.metadata)
            self._call("route", context, agent_state)
            machine.transition(ExecutionState.APPROVED, reason="runtime route established")

            for step in agent_state.steps:
                if step.status.value in {"completed", "skipped"}:
                    continue
                if not agent_state.dependencies_completed(step):
                    raise RuntimeError(f"dependencies not completed for step: {step.step_id}")
                output = self._call("execute", context, agent_state, step)
                executed_steps.append(step.step_id)
                self._call("observe", context, agent_state, step)

            machine.transition(ExecutionState.EXECUTING, reason="execution stages completed")
            machine.transition(ExecutionState.VERIFYING, reason="execution output ready for verification")
            verification = self._call("verify", context, agent_state)
            if verification is False or (verification is None and agent_state.steps and not agent_state.completed):
                revised = self._call("revise", context, agent_state)
                if revised is False:
                    raise RuntimeError("runtime verification failed after revision")
            self._call("deliver", context, agent_state)
            machine.transition(ExecutionState.COMPLETED, reason="verification and delivery completed")
        except Exception as exc:
            if machine.state not in {ExecutionState.COMPLETED, ExecutionState.FAILED}:
                machine.fail(str(exc))
            return self._result(task, machine, output, str(exc), executed_steps)

        return self._result(task, machine, output, None, executed_steps)

    def _call(self, name: str, context: RuntimeContext, state: AgentState, step: PlanStep | None = None) -> Any:
        callback = self._stages[name]
        if callback is None:
            return None
        if step is None:
            return callback(context, state)
        return callback(context, state)

    @staticmethod
    def _result(
        task: Task,
        machine: ExecutionStateMachine,
        output: Any,
        error: str | None,
        executed_steps: list[str],
    ) -> RuntimeResult:
        return RuntimeResult(
            task_id=str(task.task_id),
            state=machine.state,
            output=output,
            error=error,
            executed_steps=tuple(executed_steps),
            transitions=tuple(f"{event.from_state.value}->{event.to_state.value}" for event in machine.history),
        )
