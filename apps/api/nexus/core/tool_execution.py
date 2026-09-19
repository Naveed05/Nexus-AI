from dataclasses import dataclass
import json
import os
import signal
import threading
import time
from typing import Any, Callable, Mapping

from nexus.core.approvals import Approval, ApprovalError
from nexus.core.control_ledger import ControlLedger
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
        output_size = 0 if self.output is None else len(
            json.dumps(self.output, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        )
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
    """Execute registered tools behind security, permission, approval, and audit boundaries."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        permission_policy: PermissionPolicy | None = None,
        security_policy: ToolSecurityPolicy | None = None,
        audit_ledger: ControlLedger | None = None,
        actor: str = "system",
        sandbox_runner: Callable[[ToolSpec, dict[str, Any]], Any] | None = None,
    ) -> None:
        if not actor.strip():
            raise ValueError("actor must not be empty")
        self._registry = registry or tool_registry
        self._permission_policy = permission_policy or PermissionPolicy()
        self._security_policy = security_policy or ToolSecurityPolicy()
        self._audit_ledger = audit_ledger
        self._actor = actor.strip()
        self._sandbox_runner = sandbox_runner

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

    def _audit(self, tool_name: str, decision: PermissionDecision, reason: str) -> None:
        if self._audit_ledger is not None:
            self._audit_ledger.append(
                f"tool_execution:{tool_name}",
                self._actor,
                decision.value,
                reason,
            )

    @staticmethod
    def _run_with_timeout(tool: ToolSpec, kwargs: dict[str, Any]) -> Any:
        if os.name == "posix" and threading.current_thread() is threading.main_thread():
            def timeout_handler(signum, frame):
                raise TimeoutError(
                    f"tool execution exceeded timeout of {tool.timeout_seconds:g} seconds"
                )

            previous = signal.signal(signal.SIGALRM, timeout_handler)
            signal.setitimer(signal.ITIMER_REAL, tool.timeout_seconds)
            try:
                return tool.handler(**kwargs)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)

        started = time.perf_counter()
        output = tool.handler(**kwargs)
        elapsed = time.perf_counter() - started
        if elapsed > tool.timeout_seconds:
            raise TimeoutError(
                f"tool execution exceeded timeout of {tool.timeout_seconds:g} seconds"
            )
        return output

    def execute(
        self,
        task: Task,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        approval: Approval | None = None,
    ) -> ToolExecutionResult:
        started = time.perf_counter()
        try:
            tool = self._registry.get(tool_name)
        except ValueError as exc:
            return ToolExecutionResult(tool_name, False, error=str(exc), permission=PermissionDecision.DENY)

        try:
            # Security filtering happens before schema validation and approval
            # binding, so restricted fields cannot be smuggled into an approval.
            kwargs = self._security_policy.validate(arguments)
            kwargs = self._validate_arguments(tool, kwargs)
            decision = self._permission_policy.authorize(
                tool,
                task.risk_level,
                arguments=kwargs,
                approval=approval,
            )
        except ApprovalError as exc:
            self._audit(tool.name, PermissionDecision.APPROVAL_REQUIRED, str(exc))
            return ToolExecutionResult(
                tool.name,
                False,
                error=str(exc),
                permission=PermissionDecision.APPROVAL_REQUIRED,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except ValueError as exc:
            self._audit(tool.name, PermissionDecision.DENY, str(exc))
            return ToolExecutionResult(
                tool.name,
                False,
                error=str(exc),
                permission=PermissionDecision.DENY,
                duration_ms=(time.perf_counter() - started) * 1000,
            )

        if decision == PermissionDecision.DENY:
            self._audit(tool.name, decision, "tool execution denied by permission policy")
            return ToolExecutionResult(
                tool.name,
                False,
                error="tool execution denied by permission policy",
                permission=decision,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        if decision == PermissionDecision.APPROVAL_REQUIRED:
            self._audit(tool.name, decision, "explicit approval required for tool execution")
            return ToolExecutionResult(
                tool.name,
                False,
                error="explicit approval required for tool execution",
                permission=decision,
                duration_ms=(time.perf_counter() - started) * 1000,
            )

        try:
            if tool.sandbox_required:
                if self._sandbox_runner is None:
                    error = "sandbox-required tool cannot execute without a sandbox runner"
                    self._audit(tool.name, PermissionDecision.DENY, error)
                    return ToolExecutionResult(
                        tool.name,
                        False,
                        error=error,
                        permission=PermissionDecision.DENY,
                        duration_ms=(time.perf_counter() - started) * 1000,
                    )
                output = self._sandbox_runner(tool, kwargs)
            else:
                output = self._run_with_timeout(tool, kwargs)
            encoded_output = json.dumps(
                output, sort_keys=True, default=str, separators=(",", ":")
            ).encode("utf-8")
            if len(encoded_output) > tool.max_output_bytes:
                error = (
                    f"tool output exceeds security limit: {len(encoded_output)} "
                    f"bytes > {tool.max_output_bytes} bytes"
                )
                self._audit(tool.name, decision, error)
                return ToolExecutionResult(
                    tool.name,
                    False,
                    error=error,
                    permission=decision,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
            self._audit(tool.name, PermissionDecision.ALLOW, "tool execution completed")
            return ToolExecutionResult(
                tool.name,
                True,
                output=output,
                permission=decision,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            self._audit(tool.name, decision, f"tool execution failed: {exc}")
            return ToolExecutionResult(
                tool.name,
                False,
                error=str(exc),
                permission=decision,
                duration_ms=(time.perf_counter() - started) * 1000,
            )


tool_executor = ToolExecutor()
