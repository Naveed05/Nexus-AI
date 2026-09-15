from pathlib import Path

from nexus.core.orchestration_checkpoint import OrchestrationCheckpoint
from nexus.core.orchestrator import OrchestratorState
from nexus.core.state import StepStatus


class ResumeController:
    """Safely restore a checkpoint and expose only resumable orchestration state."""

    def __init__(self, checkpoint: OrchestrationCheckpoint | None = None) -> None:
        self._checkpoint = checkpoint or OrchestrationCheckpoint()

    def resume(self, path: str | Path) -> OrchestratorState:
        state = self._checkpoint.load(path)
        running = [step.step_id for step in state.plan.steps if step.status == StepStatus.RUNNING]
        if running:
            raise ValueError(
                f"Checkpoint contains running steps that cannot be safely resumed: {running}"
            )
        if any(step.status == StepStatus.FAILED for step in state.plan.steps):
            state.status = "failed"
            state.current_step_id = None
            return state
        state.current_step_id = None
        state.status = "completed" if not state.ready_steps() and all(
            step.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}
            for step in state.plan.steps
        ) else "ready"
        return state
