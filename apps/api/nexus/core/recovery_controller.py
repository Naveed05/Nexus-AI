from nexus.core.orchestrator import OrchestratorState
from nexus.core.recovery import RecoveryDecision, RecoveryPolicy
from nexus.core.state import StepStatus


class RecoveryController:
    """Apply bounded recovery decisions to orchestration state."""

    def __init__(self, policy: RecoveryPolicy | None = None) -> None:
        self._policy = policy or RecoveryPolicy()

    def recover(self, state: OrchestratorState, step_id: str) -> RecoveryDecision:
        step = state.plan.step_by_id(step_id)
        decision = self._policy.decide(step)
        if decision.action == "retry":
            step.status = StepStatus.PENDING
            step.error = None
            state.status = "ready"
            state.history.append(f"retry:{step_id}:attempt:{decision.next_attempt}")
        else:
            state.status = "failed"
            state.history.append(f"halt:{step_id}:attempt:{decision.next_attempt}")
        return decision
