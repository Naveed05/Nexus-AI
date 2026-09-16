from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReplanTrigger(str, Enum):
    VERIFICATION_FAILED = "verification_failed"
    EXECUTION_FAILED = "execution_failed"
    DEPENDENCY_FAILED = "dependency_failed"


@dataclass(frozen=True)
class ExecutionBudget:
    """Hard limits that keep autonomous execution bounded and observable."""

    max_steps: int = 32
    max_attempts: int = 64
    max_replans: int = 2

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.max_replans < 0:
            raise ValueError("max_replans cannot be negative")

    def can_start_step(self, completed_steps: int) -> bool:
        return 0 <= completed_steps < self.max_steps

    def can_attempt(self, attempts_used: int) -> bool:
        return 0 <= attempts_used < self.max_attempts

    def can_replan(self, replans_used: int) -> bool:
        return 0 <= replans_used < self.max_replans


@dataclass(frozen=True)
class ReplanDecision:
    """Auditable decision describing whether the agent may adapt its plan."""

    should_replan: bool
    trigger: ReplanTrigger | None
    reason: str
    replan_index: int


class AdaptiveReplanner:
    """Deterministic recovery policy; it never replans after a successful verification."""

    @staticmethod
    def decide(
        *,
        verification_passed: bool,
        execution_failed: bool = False,
        dependency_failed: bool = False,
        replans_used: int = 0,
        budget: ExecutionBudget | None = None,
    ) -> ReplanDecision:
        active_budget = budget or ExecutionBudget()
        if replans_used < 0:
            raise ValueError("replans_used cannot be negative")
        if verification_passed:
            return ReplanDecision(False, None, "Verification passed; no replan is required.", replans_used)
        if not active_budget.can_replan(replans_used):
            return ReplanDecision(False, None, "Replan budget exhausted.", replans_used)
        if dependency_failed:
            trigger = ReplanTrigger.DEPENDENCY_FAILED
            reason = "A plan dependency failed; the next plan must repair the dependency chain."
        elif execution_failed:
            trigger = ReplanTrigger.EXECUTION_FAILED
            reason = "Execution failed; the next plan may choose a different executable path."
        else:
            trigger = ReplanTrigger.VERIFICATION_FAILED
            reason = "Verification failed; the next plan must address the observable verification issue."
        return ReplanDecision(True, trigger, reason, replans_used + 1)
