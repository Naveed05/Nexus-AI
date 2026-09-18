import time
from typing import Any, Mapping

from nexus.core.permissions import PermissionDecision, PermissionPolicy
from nexus.core.task import Task
from nexus.core.tool_security import ToolSecurityPolicy
from nexus.core.tools import ToolRegistry, tool_registry
from nexus.core.tool_execution import ToolExecutionResult


class SecureToolExecutor:
    """Tool execution facade with security validation and structured results."""

    def __init__(self, registry: ToolRegistry | None = None, permission_policy: PermissionPolicy | None = None,
                 security_policy: ToolSecurityPolicy | None = None) -> None:
        self._registry = registry or tool_registry
        self._permission_policy = permission_policy or PermissionPolicy()
        self._security_policy = security_policy or ToolSecurityPolicy()

    def execute(self, task: Task, tool_name: str, arguments: Mapping[str, Any], *, approved: bool = False) -> ToolExecutionResult:
        started = time.perf_counter()
        try:
            tool = self._registry.get(tool_name)
            decision = self._permission_policy.decide(tool, task.risk_level)
            if decision == PermissionDecision.DENY:
                return ToolExecutionResult(tool.name, False, error="tool execution denied by permission policy", permission=decision)
            if decision == PermissionDecision.APPROVAL_REQUIRED and not approved:
                return ToolExecutionResult(tool.name, False, error="explicit approval required for tool execution", permission=decision)
            safe_arguments = self._security_policy.validate(arguments)
            output = tool.handler(**safe_arguments)
            return ToolExecutionResult(tool.name, True, output=output, permission=decision)
        except Exception as exc:
            return ToolExecutionResult(tool_name, False, error=str(exc),
                                       permission=locals().get("decision", PermissionDecision.DENY))
