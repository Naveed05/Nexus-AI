from dataclasses import dataclass

from nexus.core.state import PlanStep, StepStatus


@dataclass(frozen=True)
class RecoveryDecision:
    """Deterministic recovery decision for a failed orchestration step."""

    action: str
    reason: str
    next_attempt: int


class RecoveryPolicy:
    """Apply bounded, explicit retry rules without executing or mutating tools."""

    def __init__(self, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.max_attempts = max_attempts

    def decide(self, step: PlanStep) -> RecoveryDecision:
        if step.status != StepStatus.FAILED:
            raise ValueError("Recovery can only be evaluated for failed steps")

        next_attempt = step.attempts + 1
        if next_attempt <= self.max_attempts:
            return RecoveryDecision(
                action="retry",
                reason="failed step is within the configured retry budget",
                next_attempt=next_attempt,
            )
        return RecoveryDecision(
            action="halt",
            reason="retry budget exhausted; manual intervention is required",
            next_attempt=next_attempt,
        )
