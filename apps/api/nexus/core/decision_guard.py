from dataclasses import dataclass

from nexus.core.decision_engine import Decision


@dataclass(frozen=True)
class DecisionGuardResult:
    allowed: bool
    action: str
    reason: str


class DecisionGuard:
    """Applies final deterministic safety boundaries to autonomous decisions."""

    _allowed_actions = {"proceed", "stage", "review"}

    def evaluate(self, decision: Decision) -> DecisionGuardResult:
        if decision.action not in self._allowed_actions:
            return DecisionGuardResult(False, "review", "Unsupported decision action requires review.")
        if not 0.0 <= decision.confidence <= 1.0:
            return DecisionGuardResult(False, "review", "Invalid decision confidence requires review.")
        if decision.action == "proceed" and decision.confidence < 0.6:
            return DecisionGuardResult(False, "review", "Low-confidence decisions cannot proceed autonomously.")
        if decision.action == "stage" and "verify_each_stage" not in decision.safeguards:
            return DecisionGuardResult(False, "review", "Staged execution requires per-stage verification.")
        return DecisionGuardResult(True, decision.action, "Decision satisfies autonomous safety boundaries.")
