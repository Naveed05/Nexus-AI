from dataclasses import dataclass
from typing import Any, Callable

from nexus.core.orchestrator import OrchestratorState


@dataclass(frozen=True)
class VerificationDecision:
    """Immutable result of the verification gate for one completed attempt."""

    passed: bool
    reason: str


class VerificationGate:
    """Allow orchestration progression only after explicit verification succeeds."""

    def verify(
        self,
        state: OrchestratorState,
        step_id: str,
        result: Any,
        verifier: Callable[[Any], bool],
    ) -> VerificationDecision:
        step = state.plan.step_by_id(step_id)
        if step.status.value != "running":
            raise ValueError(f"Step '{step_id}' must be running before verification")
        try:
            passed = bool(verifier(result))
        except Exception as exc:
            passed = False
            reason = str(exc).strip() or exc.__class__.__name__
        else:
            reason = "verification passed" if passed else "verification failed"

        if passed:
            state.complete_step(step_id, result)
            return VerificationDecision(passed=True, reason=reason)

        state.fail_step(step_id, reason)
        return VerificationDecision(passed=False, reason=reason)
