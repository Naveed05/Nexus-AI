from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ControlRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ControlDecision:
    """Deterministic decision describing whether an agent action may proceed."""

    action: str
    risk: ControlRisk
    allowed: bool
    requires_approval: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("action must not be empty")

    def as_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "risk": self.risk.value,
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "reasons": list(self.reasons),
        }


class HumanControlPolicy:
    """Conservative action boundary for agent-controlled side effects."""

    DEFAULT_BLOCKED = frozenset({
        "credential_exfiltration",
        "security_control_bypass",
        "destructive_system_change",
        "unauthorized_access",
    })
    DEFAULT_HIGH_RISK = frozenset({
        "external_write",
        "production_deploy",
        "account_change",
        "permission_change",
        "irreversible_delete",
    })
    DEFAULT_MEDIUM_RISK = frozenset({
        "network_request",
        "file_write",
        "database_write",
        "code_execution",
    })

    def __init__(
        self,
        *,
        blocked_actions: frozenset[str] = DEFAULT_BLOCKED,
        high_risk_actions: frozenset[str] = DEFAULT_HIGH_RISK,
        medium_risk_actions: frozenset[str] = DEFAULT_MEDIUM_RISK,
    ) -> None:
        self.blocked_actions = frozenset(self._normalize(action) for action in blocked_actions)
        self.high_risk_actions = frozenset(self._normalize(action) for action in high_risk_actions)
        self.medium_risk_actions = frozenset(self._normalize(action) for action in medium_risk_actions)
        if self.blocked_actions & self.high_risk_actions or self.blocked_actions & self.medium_risk_actions:
            raise ValueError("blocked actions cannot also be risk-tiered")

    @staticmethod
    def _normalize(action: str) -> str:
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action must be a non-empty string")
        return action.strip().lower()

    def evaluate(self, action: str, *, approved: bool = False) -> ControlDecision:
        normalized = self._normalize(action)
        if normalized in self.blocked_actions:
            return ControlDecision(normalized, ControlRisk.BLOCKED, False, False, ("action is permanently blocked by human-control policy",))
        if normalized in self.high_risk_actions:
            if not approved:
                return ControlDecision(normalized, ControlRisk.HIGH, False, True, ("high-risk side effect requires explicit human approval",))
            return ControlDecision(normalized, ControlRisk.HIGH, True, False, ("explicit human approval supplied",))
        if normalized in self.medium_risk_actions:
            return ControlDecision(normalized, ControlRisk.MEDIUM, True, False, ("medium-risk action is allowed within the execution boundary",))
        return ControlDecision(normalized, ControlRisk.LOW, True, False, ("action is not classified as a restricted side effect",))
