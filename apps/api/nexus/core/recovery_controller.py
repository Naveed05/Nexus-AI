from nexus.core.orchestration_audit import OrchestrationAudit
from nexus.core.orchestrator import OrchestratorState
from nexus.core.recovery import RecoveryDecision, RecoveryPolicy
from nexus.core.state import StepStatus


class RecoveryController:
    """Apply bounded recovery decisions to orchestration state and audit them."""

    def __init__(
        self,
        policy: RecoveryPolicy | None = None,
        audit: OrchestrationAudit | None = None,
    ) -> None:
        self._policy = policy or RecoveryPolicy()
        self._audit = audit or OrchestrationAudit()

    @property
    def audit(self) -> OrchestrationAudit:
        return self._audit

    def recover(self, state: OrchestratorState, step_id: str) -> RecoveryDecision:
        step = state.plan.step_by_id(step_id)
        decision = self._policy.decide(step)
        if decision.action == "retry":
            step.status = StepStatus.PENDING
            step.error = None
            step.attempts = decision.next_attempt
            state.status = "ready"
            state.history.append(f"retry:{step_id}:attempt:{decision.next_attempt}")
            self._audit.record(
                "retry",
                step_id,
                attempt=decision.next_attempt,
                reason=decision.reason,
            )
        else:
            state.status = "failed"
            state.history.append(f"halt:{step_id}:attempt:{decision.next_attempt}")
            self._audit.record(
                "halt",
                step_id,
                attempt=decision.next_attempt,
                reason=decision.reason,
            )
        return decision
