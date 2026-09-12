from dataclasses import dataclass
import inspect

from nexus.core.events import EventType, ExecutionEvent
from nexus.core.executor import ExecutionResult, ModelExecutor
from nexus.core.models import ModelSpec
from nexus.core.planner import TaskPlanner
from nexus.core.router import RoutingDecision, TaskRouter
from nexus.core.state import AgentState, PlanStep, StepStatus
from nexus.core.task import Task
from nexus.core.tool_intelligence import ToolSelector
from nexus.core.verification import OutputVerifier, VerificationResult
from nexus.core.workspaces import WorkspaceNotFoundError, workspace_registry


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry policy for recoverable agent execution failures."""

    max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    def attempts(self) -> range:
        return range(1, self.max_attempts + 1)


@dataclass(frozen=True)
class RouteResult:
    task: Task
    model: ModelSpec
    decision: RoutingDecision


@dataclass(frozen=True)
class EngineResult:
    task: Task
    model: ModelSpec
    execution: ExecutionResult
    state: AgentState
    verification: VerificationResult
    events: tuple[ExecutionEvent, ...]


class NexusEngine:
    """Coordinates routing, planning, tool selection, execution, recovery, and verification."""

    def __init__(
        self,
        router: TaskRouter | None = None,
        executor: ModelExecutor | None = None,
        planner: TaskPlanner | None = None,
        verifier: OutputVerifier | None = None,
        tool_selector: ToolSelector | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._router = router or TaskRouter()
        self._executor = executor or ModelExecutor()
        self._planner = planner or TaskPlanner()
        self._verifier = verifier or OutputVerifier()
        self._tool_selector = tool_selector or ToolSelector()
        self._retry_policy = retry_policy or RetryPolicy()

    def route_task(self, task: Task) -> RouteResult:
        """Select the model and expose safe routing metadata without executing it."""
        decision = self._router.decide(task)
        return RouteResult(task=task, model=decision.model, decision=decision)

    def _resolve_workspace_context(self, task: Task) -> Task:
        """Attach workspace resource references before planning or tool selection."""
        if task.workspace_id is None:
            return task
        try:
            context = workspace_registry.context(task.workspace_id)
        except WorkspaceNotFoundError:
            raise

        workspace_text = context.as_text()
        existing = task.context.strip() if task.context else ""
        if workspace_text in existing:
            return task
        return task.model_copy(
            update={
                "context": "\n".join(part for part in (existing, workspace_text) if part) or None,
            }
        )

    def _execute_compatibly(
        self,
        task: Task,
        model: ModelSpec,
        allowed_tools: tuple[str, ...],
    ) -> ExecutionResult:
        """Call both current executors and older test/custom executors safely."""
        execute = self._executor.execute
        try:
            signature = inspect.signature(execute)
            accepts_allowed_tools = "allowed_tools" in signature.parameters
        except (TypeError, ValueError):
            accepts_allowed_tools = True

        if accepts_allowed_tools:
            return execute(task, model, allowed_tools=allowed_tools)
        return execute(task, model)

    def _run_with_recovery(
        self,
        task: Task,
        model: ModelSpec,
        step: PlanStep,
        events: list[ExecutionEvent],
        allowed_tools: tuple[str, ...],
    ) -> ExecutionResult:
        last_error: Exception | None = None

        for attempt in self._retry_policy.attempts():
            step.attempts = attempt
            try:
                execution = self._execute_compatibly(task, model, allowed_tools)
                if attempt > 1:
                    events.append(
                        ExecutionEvent(
                            event_type=EventType.EXECUTION_RECOVERED,
                            task_id=task.task_id,
                            message="Execution recovered after a retry.",
                            data={"step_id": step.step_id, "attempt": attempt},
                        )
                    )
                return execution
            except Exception as exc:
                last_error = exc
                step.error = str(exc)
                events.append(
                    ExecutionEvent(
                        event_type=EventType.STEP_FAILED,
                        task_id=task.task_id,
                        message="Execution attempt failed.",
                        data={
                            "step_id": step.step_id,
                            "attempt": attempt,
                            "error_type": type(exc).__name__,
                        },
                    )
                )
                if attempt < self._retry_policy.max_attempts:
                    events.append(
                        ExecutionEvent(
                            event_type=EventType.RETRY_SCHEDULED,
                            task_id=task.task_id,
                            message="Retrying the failed execution step.",
                            data={
                                "step_id": step.step_id,
                                "next_attempt": attempt + 1,
                            },
                        )
                    )

        assert last_error is not None
        raise last_error

    def _step_task(self, task: Task, step: PlanStep, state: AgentState) -> Task:
        """Create an isolated task view for one executable plan step."""
        completed_outputs = [
            f"{item.step_id}: {item.result}"
            for item in state.steps
            if item.status == StepStatus.COMPLETED and item.result is not None
        ]
        context_parts = [part for part in (task.context, *completed_outputs) if part]
        return task.model_copy(
            update={
                "objective": step.objective,
                "context": "\n".join(context_parts) or None,
            }
        )

    def run(self, task: Task) -> EngineResult:
        task = self._resolve_workspace_context(task)
        route = self.route_task(task)
        state = AgentState(task_id=task.task_id, objective=task.objective)
        events: list[ExecutionEvent] = [
            ExecutionEvent(
                event_type=EventType.TASK_STARTED,
                task_id=task.task_id,
                message="NEXUS task execution started.",
            ),
            ExecutionEvent(
                event_type=EventType.MODEL_ROUTED,
                task_id=task.task_id,
                message=f"Task routed to {route.model.model_id}.",
                data={
                    "model_key": route.model.key,
                    "model_id": route.model.model_id,
                    "provider": route.model.provider,
                    "tier": route.model.tier,
                    "score": route.decision.score,
                    "reasons": list(route.decision.reasons),
                },
            ),
        ]

        state.steps = self._planner.plan(task)
        state.metadata["plan_type"] = (
            "data" if any(step.step_id in {"inspect_data", "analyze_data"} for step in state.steps)
            else "coding" if any(step.step_id in {"inspect_code", "implement"} for step in state.steps)
            else "research" if any(step.step_id in {"research", "synthesize"} for step in state.steps)
            else "general"
        )
        events.append(
            ExecutionEvent(
                event_type=EventType.PLAN_CREATED,
                task_id=task.task_id,
                message=f"Created {len(state.steps)} execution steps.",
                data={
                    "step_count": len(state.steps),
                    "step_ids": [step.step_id for step in state.steps],
                    "plan_type": state.metadata["plan_type"],
                },
            )
        )

        execution: ExecutionResult | None = None
        for index, step in enumerate(state.steps):
            state.current_step_index = index
            if not state.dependencies_completed(step):
                step.status = StepStatus.FAILED
                step.error = "Step dependencies were not completed."
                raise RuntimeError(f"Cannot execute step '{step.step_id}': dependencies incomplete")

            if not step.execution_required:
                step.status = StepStatus.COMPLETED
                step.observation = "Kernel-managed step completed without model execution."
                events.append(
                    ExecutionEvent(
                        event_type=EventType.STEP_COMPLETED,
                        task_id=task.task_id,
                        message=f"Planning/control step completed: {step.step_id}.",
                        data={"step_id": step.step_id, "execution_required": False},
                    )
                )
                continue

            step.status = StepStatus.RUNNING
            events.append(
                ExecutionEvent(
                    event_type=EventType.STEP_STARTED,
                    task_id=task.task_id,
                    message=f"Executing plan step: {step.step_id}.",
                    data={"step_id": step.step_id, "objective": step.objective},
                )
            )

            decision = self._tool_selector.select(task, step)
            step.selected_tool = decision.tool.name if decision.tool else None
            step.tool_score = decision.score
            allowed_tools = (decision.tool.name,) if decision.tool is not None else ()
            events.append(
                ExecutionEvent(
                    event_type=EventType.TOOL_SELECTED,
                    task_id=task.task_id,
                    message=(
                        f"Selected tool: {decision.tool.name}."
                        if decision.tool is not None
                        else "No tool selected for this step."
                    ),
                    data={
                        "step_id": step.step_id,
                        "tool_name": step.selected_tool,
                        "score": decision.score,
                        "reasons": list(decision.reasons),
                    },
                )
            )

            if decision.tool is not None:
                events.append(
                    ExecutionEvent(
                        event_type=EventType.TOOL_AUTHORIZATION,
                        task_id=task.task_id,
                        message=f"Tool '{decision.tool.name}' authorized for execution.",
                        data={
                            "step_id": step.step_id,
                            "tool_name": decision.tool.name,
                            "risk_level": decision.tool.risk_level,
                            "permission": decision.tool.permission,
                        },
                    )
                )

            step_task = self._step_task(task, step, state)
            try:
                execution = self._run_with_recovery(
                    step_task,
                    route.model,
                    step,
                    events,
                    allowed_tools=allowed_tools,
                )
            except Exception as exc:
                step.status = StepStatus.FAILED
                events.append(
                    ExecutionEvent(
                        event_type=EventType.TASK_FAILED,
                        task_id=task.task_id,
                        message="NEXUS task failed after exhausting execution retries.",
                        data={
                            "step_id": step.step_id,
                            "error_type": type(exc).__name__,
                            "attempts": step.attempts,
                        },
                    )
                )
                raise

            step.result = execution.output
            step.observation = {
                "response_id": execution.response_id,
                "tool_call_count": len(execution.tool_calls),
                "tool_names": [call.tool_name for call in execution.tool_calls],
            }
            step.status = StepStatus.COMPLETED

            for call in execution.tool_calls:
                events.append(
                    ExecutionEvent(
                        event_type=EventType.TOOL_CALLED,
                        task_id=task.task_id,
                        message=f"Tool executed: {call.tool_name}.",
                        data={"tool_name": call.tool_name, "step_id": step.step_id},
                    )
                )

            events.append(
                ExecutionEvent(
                    event_type=EventType.STEP_COMPLETED,
                    task_id=task.task_id,
                    message=f"Execution step completed: {step.step_id}.",
                    data={"step_id": step.step_id, "attempts": step.attempts},
                )
            )

        if execution is None:
            raise RuntimeError("Execution plan contained no executable step")

        verification_step = next(step for step in state.steps if step.step_id == "verify")
        events.append(
            ExecutionEvent(
                event_type=EventType.VERIFICATION_STARTED,
                task_id=task.task_id,
                message="Running observable output verification.",
                data={"step_id": verification_step.step_id},
            )
        )

        verification = self._verifier.verify(task, execution.output, execution.tool_calls)
        state.verification_passed = verification.passed
        verification_step.result = verification.checks
        verification_step.observation = {"issues": verification.issues}
        verification_step.error = "; ".join(verification.issues) or None
        verification_step.status = StepStatus.COMPLETED if verification.passed else StepStatus.FAILED

        events.append(
            ExecutionEvent(
                event_type=EventType.VERIFICATION_COMPLETED,
                task_id=task.task_id,
                message="Output verification completed.",
                data={"passed": verification.passed, "checks": verification.checks},
            )
        )

        for step in state.steps:
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.SKIPPED
        state.current_step_index = len(state.steps)

        events.append(
            ExecutionEvent(
                event_type=EventType.TASK_COMPLETED if verification.passed else EventType.TASK_FAILED,
                task_id=task.task_id,
                message=(
                    "NEXUS task completed successfully."
                    if verification.passed
                    else "NEXUS task failed output verification."
                ),
            )
        )

        return EngineResult(
            task=task,
            model=route.model,
            execution=execution,
            state=state,
            verification=verification,
            events=tuple(events),
        )


engine = NexusEngine()
