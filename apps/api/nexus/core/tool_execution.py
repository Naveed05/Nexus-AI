from dataclasses import dataclass
import json
import time
from typing import Any, Mapping

from nexus.core.permissions import PermissionDecision, PermissionPolicy
from nexus.core.task import Task
from nexus.core.tool_security import ToolSecurityPolicy
from nexus.core.tools import ToolRegistry, ToolSpec, tool_registry


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    success: bool
    output: Any | None = None
    error: str | None = None
    permission: PermissionDecision = PermissionDecision.ALLOW
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        output_size = 0 if self.output is None else len(json.dumps(self.output, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8"))
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "permission": self.permission.value,
            "duration_ms": self.duration_ms,
            "output_size_bytes": output_size,
        }


class ToolExecutor:
    """Execute explicitly registered tools behind one permission boundary."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        permission_policy: PermissionPolicy | None = None,
        security_policy: ToolSecurityPolicy | None = None,
    ) -> None:
        self._registry = registry or tool_registry
        self._permission_policy = permission_policy or PermissionPolicy()
        self._security_policy = security_policy or ToolSecurityPolicy()

    @staticmethod
    def _validate_arguments(tool: ToolSpec, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise ValueError("tool arguments must be an object")
        schema = tool.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in arguments]
        if missing:
            raise ValueError(f"missing required tool arguments: {', '.join(sorted(missing))}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(arguments) - set(properties))
            if unknown:
                raise ValueError(f"unknown tool arguments: {', '.join(unknown)}")
        return dict(arguments)

    def execute(
        self,
        task: Task,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        approved: bool = False,
    ) -> ToolExecutionResult:
        started = time.perf_counter()
        try:
            tool = self._registry.get(tool_name)
        except ValueError as exc:
            return ToolExecutionResult(tool_name, False, error=str(exc), permission=PermissionDecision.DENY)

        decision = self._permission_policy.decide(tool, task.risk_level)
        if decision == PermissionDecision.DENY:
            return ToolExecutionResult(tool.name, False, error="tool execution denied by permission policy", permission=decision)
        if decision == PermissionDecision.APPROVAL_REQUIRED and not approved:
            return ToolExecutionResult(tool.name, False, error="explicit approval required for tool execution", permission=decision)

        try:
            kwargs = self._validate_arguments(tool, arguments)
            kwargs = self._security_policy.validate(kwargs)
            output = tool.handler(**kwargs)
            return ToolExecutionResult(tool.name, True, output=output, permission=decision, duration_ms=(time.perf_counter() - started) * 1000)
        except Exception as exc:
            return ToolExecutionResult(tool.name, False, error=str(exc), permission=decision, duration_ms=(time.perf_counter() - started) * 1000)


tool_executor = ToolExecutor()
