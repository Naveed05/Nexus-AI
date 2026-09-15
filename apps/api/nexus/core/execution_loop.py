from dataclasses import dataclass
from typing import Any, Callable

from nexus.core.execution_coordinator import ExecutionCoordinator, ExecutionDecision
from nexus.core.orchestrator import OrchestratorState
from nexus.core.task import Task


@dataclass(frozen=True)
class ExecutionResult:
    """Result of one controlled orchestration execution attempt."""

    decision: ExecutionDecision
    result: Any | None
    error: str | None = None


class OrchestrationExecutor:
    """Execute ready plan steps through an explicit injected execution boundary."""

    def __init__(self, coordinator: ExecutionCoordinator | None = None) -> None:
        self._coordinator = coordinator or ExecutionCoordinator()

    def execute_step(
        self,
        task: Task,
        state: OrchestratorState,
        step_id: str,
        executor: Callable[[ExecutionDecision], Any],
    ) -> ExecutionResult:
        decision = self._coordinator.prepare(task, state, step_id)
        step = state.start_step(step_id)
        step.attempts += 1
        try:
            result = executor(decision)
        except Exception as exc:
            error = str(exc).strip() or exc.__class__.__name__
            state.fail_step(step_id, error)
            return ExecutionResult(decision=decision, result=None, error=error)
        state.complete_step(step_id, result)
        return ExecutionResult(decision=decision, result=result)

    def execute_next(
        self,
        task: Task,
        state: OrchestratorState,
        executor: Callable[[ExecutionDecision], Any],
    ) -> ExecutionResult | None:
        """Execute the first ready step in deterministic plan order."""
        ready = state.ready_steps()
        if not ready:
            return None
        return self.execute_step(task, state, ready[0].step_id, executor)
