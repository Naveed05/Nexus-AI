from enum import Enum

from nexus.core.task import RiskLevel
from nexus.core.tools import ToolSpec


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    DENY = "deny"


class PermissionPolicy:
    """Central policy gate for tool execution."""

    def decide(self, tool: ToolSpec, task_risk: RiskLevel) -> PermissionDecision:
        if tool.risk_level == "high" or task_risk == RiskLevel.HIGH:
            return PermissionDecision.APPROVAL_REQUIRED
        if tool.risk_level == "medium" and task_risk == RiskLevel.MEDIUM:
            return PermissionDecision.APPROVAL_REQUIRED
        return PermissionDecision.ALLOW


permission_policy = PermissionPolicy()
