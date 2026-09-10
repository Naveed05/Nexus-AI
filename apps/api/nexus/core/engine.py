from dataclasses import dataclass

from nexus.core.events import EventType, ExecutionEvent
from nexus.core.executor import ExecutionResult, ModelExecutor
from nexus.core.models import ModelSpec
from nexus.core.planner import TaskPlanner
from nexus.core.router import TaskRouter
from nexus.core.state import AgentState, StepStatus
from nexus.core.task import Task


@dataclass(frozen=True)
class RouteResult:
    task: Task
    model: ModelSpec


@dataclass(frozen=True)
class EngineResult:
    task: Task
    model: ModelSpec
    execution: ExecutionResult
    state: AgentState
    events: tuple[ExecutionEvent, ...]


class NexusEngine:
    """Coordinates routing, planning, execution, and first-pass verification."""

    def __init__(
        self,
        router: TaskRouter | None = None,
        executor: ModelExecutor | None = None,
        planner: TaskPlanner | None = None,
    ) -> None:
        self._router = router or TaskRouter()
        self._executor = executor or ModelExecutor()
        self._planner = planner or TaskPlanner()

    def route_task(self, task: Task) -> RouteResult:
        """Select the model without executing it."""
        return RouteResult(task=task, model=self._router.route(task))

    def run(self, task: Task) -> EngineResult:
        route = self.route_task(task)
        state = AgentState(task_id=task.task_id, objective=task.objective)
        events: list[ExecutionEvent] = [
            ExecutionEvent(
                event_type=EventType.TASK_STARTED,
                task_id=task.task_id,
                message="NEXUS task execution started.",
            )
        ]

        state.steps = self._planner.plan(task)
        events.append(
            ExecutionEvent(
                event_type=EventType.PLAN_CREATED,
                task_id=task.task_id,
                message=f"Created {len(state.steps)} execution steps.",
                data={"step_count": len(state.steps)},
            )
        )

        execute_step = next(step for step in state.steps if step.step_id == "execute")
        execute_step.status = StepStatus.RUNNING
        execute_step.attempts += 1
        events.append(
            ExecutionEvent(
                event_type=EventType.STEP_STARTED,
                task_id=task.task_id,
                message="Executing the selected model workflow.",
                data={"step_id": execute_step.step_id},
            )
        )

        execution = self._executor.execute(task, route.model)
        execute_step.result = execution.output
        execute_step.status = StepStatus.COMPLETED

        for call in execution.tool_calls:
            events.append(
                ExecutionEvent(
                    event_type=EventType.TOOL_CALLED,
                    task_id=task.task_id,
                    message=f"Tool executed: {call.tool_name}.",
                    data={"tool_name": call.tool_name},
                )
            )

        events.append(
            ExecutionEvent(
                event_type=EventType.STEP_COMPLETED,
                task_id=task.task_id,
                message="Model execution completed.",
                data={"step_id": execute_step.step_id},
            )
        )

        verification_step = next(step for step in state.steps if step.step_id == "verify")
        verification_step.status = StepStatus.RUNNING
        events.append(
            ExecutionEvent(
                event_type=EventType.VERIFICATION_STARTED,
                task_id=task.task_id,
                message="Running first-pass output verification.",
            )
        )

        state.verification_passed = bool(execution.output.strip())
        verification_step.result = {"non_empty_output": state.verification_passed}
        verification_step.status = (
            StepStatus.COMPLETED if state.verification_passed else StepStatus.FAILED
        )
        events.append(
            ExecutionEvent(
                event_type=EventType.VERIFICATION_COMPLETED,
                task_id=task.task_id,
                message="Output verification completed.",
                data={"passed": state.verification_passed},
            )
        )

        for step in state.steps:
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.SKIPPED
        state.current_step_index = len(state.steps)

        if state.verification_passed:
            events.append(
                ExecutionEvent(
                    event_type=EventType.TASK_COMPLETED,
                    task_id=task.task_id,
                    message="NEXUS task completed successfully.",
                )
            )
        else:
            events.append(
                ExecutionEvent(
                    event_type=EventType.TASK_FAILED,
                    task_id=task.task_id,
                    message="NEXUS task failed output verification.",
                )
            )

        return EngineResult(
            task=task,
            model=route.model,
            execution=execution,
            state=state,
            events=tuple(events),
        )


engine = NexusEngine()
