from datetime import datetime, timezone, timedelta

import pytest

from nexus.core.approvals import issue_approval
from nexus.core.control_ledger import ControlLedger
from nexus.core.task import RiskLevel, Task
from nexus.core.tool_execution import ToolExecutor
from nexus.core.tools import ToolSpec, ToolRegistry


def _risky_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "risky", "Risky operation", {
            "type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False,
        }, "medium", lambda value: value,
    ))
    return registry


def test_tool_executor_runs_registered_tool() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "echo", "Echo text", {
            "type": "object",
            "properties": {"text": {"type": "string"}}, 
            "required": ["text"],
            "additionalProperties": False,
        }, "low", lambda text: {"text": text},
    ))
    result = ToolExecutor(registry=registry).execute(Task(objective="echo"), "echo", {"text": "hello"})
    assert result.success is True
    assert result.output == {"text": "hello"}


def test_tool_executor_rejects_invalid_arguments() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "echo", "Echo text", {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }, "low", lambda text: {"text": text},
    ))
    result = ToolExecutor(registry=registry).execute(Task(objective="echo"), "echo", {})
    assert result.success is False
    assert "missing required" in result.error


def test_tool_executor_requires_provenance_bound_approval_for_medium_risk() -> None:
    registry = _risky_registry()
    executor = ToolExecutor(registry=registry)
    task = Task(objective="risky", risk_level=RiskLevel.MEDIUM)

    blocked = executor.execute(task, "risky", {"value": "hello"})
    assert blocked.success is False
    assert blocked.permission.value == "approval_required"

    approval = issue_approval(approver="reviewer", tool_name="risky", arguments={"value": "hello"}, ttl_seconds=60)
    allowed = executor.execute(task, "risky", {"value": "hello"}, approval=approval)
    assert allowed.success is True
    assert allowed.output == "hello"


def test_tool_executor_rejects_mismatched_approval() -> None:
    registry = _risky_registry()
    executor = ToolExecutor(registry=registry)
    task = Task(objective="risky", risk_level=RiskLevel.MEDIUM)
    approval = issue_approval(approver="reviewer", tool_name="risky", arguments={"value": "approved"}, ttl_seconds=60)

    result = executor.execute(task, "risky", {"value": "different"}, approval=approval)
    assert result.success is False
    assert result.permission.value == "approval_required"
    assert "fingerprint" in result.error


def test_tool_executor_rejects_expired_approval() -> None:
    registry = _risky_registry()
    executor = ToolExecutor(registry=registry)
    task = Task(objective="risky", risk_level=RiskLevel.MEDIUM)
    issued = datetime.now(timezone.utc) - timedelta(minutes=10)
    approval = issue_approval(
        approver="reviewer",
        tool_name="risky",
        arguments={"value": "hello"},
        ttl_seconds=1,
        now=issued,
    )

    result = executor.execute(task, "risky", {"value": "hello"}, approval=approval)
    assert result.success is False
    assert "expired" in result.error


def test_tool_executor_audits_permission_and_execution_events(tmp_path) -> None:
    ledger = ControlLedger(tmp_path / "controls.json")
    executor = ToolExecutor(registry=_risky_registry(), audit_ledger=ledger, actor="reviewer")
    task = Task(objective="risky", risk_level=RiskLevel.MEDIUM)

    blocked = executor.execute(task, "risky", {"value": "hello"})
    assert blocked.success is False

    approval = issue_approval(approver="reviewer", tool_name="risky", arguments={"value": "hello"}, ttl_seconds=60)
    allowed = executor.execute(task, "risky", {"value": "hello"}, approval=approval)
    assert allowed.success is True

    events = ledger.audit(action="tool_execution:risky")
    assert len(events) == 2
    assert events[0].decision == "allow"
    assert events[1].decision == "approval_required"
    assert all(event.actor == "reviewer" for event in events)


def test_tool_executor_rejects_oversized_output() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "large", "Large output", {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False,
        }, "low", lambda: {"payload": "x" * 100}, max_output_bytes=32,
    ))
    result = ToolExecutor(registry=registry).execute(Task(objective="large"), "large", {})
    assert result.success is False
    assert result.output is None
    assert "output exceeds security limit" in result.error


def test_tool_spec_rejects_invalid_output_limit() -> None:
    with pytest.raises(ValueError, match="max_output_bytes"):
        ToolSpec(
            "invalid", "Invalid", {"type": "object"}, "low", lambda: None,
            max_output_bytes=0,
        )


def test_tool_executor_failures_are_structured() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "boom", "Failing operation", {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False,
        }, "low", lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    ))
    result = ToolExecutor(registry=registry).execute(Task(objective="boom"), "boom", {})
    assert result.success is False
    assert result.error == "boom"


def test_tool_executor_applies_security_policy() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "echo", "Echo text", {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }, "low", lambda text: {"text": text},
    ))
    result = ToolExecutor(registry=registry).execute(
        Task(objective="echo"), "echo", {"text": "ok", "password": "secret"}
    )
    assert result.success is False
    assert "restricted fields" in result.error


def test_tool_execution_result_is_structured() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "echo", "Echo text", {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }, "low", lambda text: {"text": text},
    ))
    result = ToolExecutor(registry=registry).execute(Task(objective="echo"), "echo", {"text": "hello"})
    payload = result.as_dict()
    assert result.success is True
    assert payload["tool_name"] == "echo"
    assert payload["output_size_bytes"] > 0
    assert payload["duration_ms"] >= 0
