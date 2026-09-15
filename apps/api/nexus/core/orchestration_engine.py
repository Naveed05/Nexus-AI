from dataclasses import dataclass
from typing import Any, Callable

from nexus.core.execution_coordinator import ExecutionCoordinator
from nexus.core.execution_loop import ExecutionResult, OrchestrationExecutor
from nexus.core.orchestration_audit import OrchestrationAudit
from nexus.core.orchestration_checkpoint import OrchestrationCheckpoint
from nexus.core.orchestrator import OrchestratorState, TaskDecomposer
from nexus.core.recovery_controller import RecoveryController
from nexus.core.task import Task


@dataclass(frozen=True)
class OrchestrationRun:
    """Bounded summary of one autonomous orchestration run."""

    status: str
    steps_executed: int
    retries: int
    results: tuple[ExecutionResult, ...]


class OrchestrationEngine:
    """Drive planning, execution, verification, recovery, audit, and checkpoints."""

    def __init__(
        self,
        decomposer: TaskDecomposer | None = None,
        executor: OrchestrationExecutor | None = None,
        recovery: RecoveryController | None = None,
        audit: OrchestrationAudit | None = None,
        checkpoint: OrchestrationCheckpoint | None = None,
    ) -> None:
        self._decomposer = decomposer or TaskDecomposer()
        self._audit = audit or OrchestrationAudit()
        self._executor = executor or OrchestrationExecutor(
            coordinator=ExecutionCoordinator(), audit=self._audit
        )
        self._recovery = recovery or RecoveryController(audit=self._audit)
        self._checkpoint = checkpoint or OrchestrationCheckpoint()

    @property
    def audit(self) -> OrchestrationAudit:
        return self._audit

    def run(
        self,
        task: Task,
        executor: Callable[[Any], Any],
        verifier: Callable[[Any], bool],
        checkpoint_path: str | None = None,
        max_cycles: int = 100,
    ) -> OrchestrationRun:
        if max_cycles < 1:
            raise ValueError("max_cycles must be at least 1")
        state = OrchestratorState(plan=self._decomposer.decompose(task))
        results: list[ExecutionResult] = []
        retries = 0

        for _ in range(max_cycles):
            if state.status == "completed":
                break
            ready = state.ready_steps()
            if not ready:
                if state.status == "failed":
                    step_id = state.current_step_id
                    if step_id:
                        decision = self._recovery.recover(state, step_id)
                        if decision.action == "retry":
                            retries += 1
                            continue
                break

            result = self._executor.execute_next(task, state, executor, verifier)
            if result is None:
                break
            results.append(result)
            if result.error is not None and state.status == "failed":
                failed_step = next(
                    step for step in state.plan.steps if step.error == result.error
                )
                decision = self._recovery.recover(state, failed_step.step_id)
                if decision.action == "retry":
                    retries += 1
                else:
                    break
            if checkpoint_path:
                self._checkpoint.save(state, checkpoint_path)

        if checkpoint_path:
            self._checkpoint.save(state, checkpoint_path)
        return OrchestrationRun(
            status=state.status,
            steps_executed=len(results),
            retries=retries,
            results=tuple(results),
        )
