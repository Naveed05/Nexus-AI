from enum import Enum

from nexus.core.task import RiskLevel
from nexus.core.tools import ToolSpec


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    DENY = "deny"


class PermissionPolicy:
    """Central policy gate for tool execution.

    Risk is evaluated separately from the tool's permission level. Medium and
    high-risk tools require explicit approval; modify tools require at least a
    medium-risk task; high-risk tools always require approval.
    """

    _risk_rank = {"low": 0, "medium": 1, "high": 2}

    def decide(self, tool: ToolSpec, task_risk: RiskLevel) -> PermissionDecision:
        task_rank = self._risk_rank[task_risk.value]
        tool_rank = self._risk_rank[tool.risk_level]

        if tool_rank > task_rank:
            return PermissionDecision.DENY
        if tool.permission == "high_risk" or tool.risk_level == "high":
            return PermissionDecision.APPROVAL_REQUIRED
        if tool.permission == "modify" and task_rank < 1:
            return PermissionDecision.DENY
        if tool.risk_level == "medium":
            return PermissionDecision.APPROVAL_REQUIRED
        return PermissionDecision.ALLOW


permission_policy = PermissionPolicy()
