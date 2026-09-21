from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class AutonomyDecision(str, Enum):
    CONTINUE = "continue"
    REVISE = "revise"
    COMPLETE = "complete"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class VerificationSignal:
    passed: bool
    confidence: float
    issues: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class AutonomyPolicy:
    min_completion_confidence: float = 0.85
    min_revision_confidence: float = 0.60
    max_revisions: int = 3
    require_evidence: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_revision_confidence <= self.min_completion_confidence <= 1.0:
            raise ValueError("confidence thresholds must be ordered between 0 and 1")
        if self.max_revisions < 0:
            raise ValueError("max_revisions cannot be negative")


@dataclass
class AutonomyState:
    revisions: int = 0
    decisions: list[AutonomyDecision] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


class AutonomyController:
    """Bounded observe-verify-revise loop; it never grants itself authority beyond policy."""

    def __init__(self, policy: AutonomyPolicy | None = None) -> None:
        self.policy = policy or AutonomyPolicy()

    def decide(self, signal: VerificationSignal, state: AutonomyState) -> AutonomyDecision:
        if signal.passed and signal.confidence >= self.policy.min_completion_confidence and (
            not self.policy.require_evidence or bool(signal.evidence)
        ):
            decision = AutonomyDecision.COMPLETE
        elif state.revisions >= self.policy.max_revisions:
            decision = AutonomyDecision.ESCALATE
        elif signal.confidence >= self.policy.min_revision_confidence:
            decision = AutonomyDecision.REVISE
        else:
            decision = AutonomyDecision.ESCALATE
        state.decisions.append(decision)
        state.issues.extend(issue for issue in signal.issues if issue not in state.issues)
        state.evidence.extend(item for item in signal.evidence if item not in state.evidence)
        if decision is AutonomyDecision.REVISE:
            state.revisions += 1
        return decision

    def run_loop(
        self,
        execute: Callable[[int], Any],
        verify: Callable[[Any, int], VerificationSignal],
        *,
        state: AutonomyState | None = None,
    ) -> tuple[Any, AutonomyState, AutonomyDecision]:
        current = state or AutonomyState()
        result: Any = None
        while True:
            result = execute(current.revisions)
            signal = verify(result, current.revisions)
            decision = self.decide(signal, current)
            if decision is not AutonomyDecision.REVISE:
                return result, current, decision
