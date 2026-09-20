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


def test_tool_executor_enforces_timeout() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "slow", "Slow operation", {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False,
        }, "low", lambda: __import__("time").sleep(0.05), timeout_seconds=0.01,
    ))
    result = ToolExecutor(registry=registry).execute(Task(objective="slow"), "slow", {})
    assert result.success is False
    assert result.output is None
    assert "exceeded timeout" in result.error


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

def test_tool_executor_fails_closed_for_sandbox_required_tool_without_runner() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "sandboxed", "Sandboxed operation", {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False,
        }, "low", lambda: "unsafe-direct-path", sandbox_required=True,
    ))
    result = ToolExecutor(registry=registry).execute(Task(objective="sandboxed"), "sandboxed", {})
    assert result.success is False
    assert result.permission.value == "deny"
    assert "sandbox runner" in result.error


def test_tool_executor_routes_sandbox_required_tool_to_runner() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "sandboxed", "Sandboxed operation", {
            "type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"],
            "additionalProperties": False,
        }, "low", lambda value: "direct-handler", sandbox_required=True,
    ))
    calls = []

    def runner(tool, arguments):
        calls.append((tool.name, arguments))
        return {"sandboxed": arguments["value"]}

    result = ToolExecutor(registry=registry, sandbox_runner=runner).execute(
        Task(objective="sandboxed"), "sandboxed", {"value": "hello"}
    )
    assert result.success is True
    assert result.output == {"sandboxed": "hello"}
    assert calls == [("sandboxed", {"value": "hello"})]



def test_tool_health_tracks_success_and_failure_state() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "echo", "Echo text", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        "low", lambda text: {"text": text},
    ))
    health = __import__("nexus.core.tool_execution", fromlist=["ToolHealthRegistry"]).ToolHealthRegistry(
        failure_threshold=2, cooldown_seconds=60
    )
    executor = ToolExecutor(registry=registry, health_registry=health)
    task = Task(objective="echo")

    first = executor.execute(task, "echo", {"text": "hello"})
    assert first.success is True
    snapshot = executor.health("echo")
    assert snapshot.executions == 1
    assert snapshot.successes == 1
    assert snapshot.consecutive_failures == 0
    assert snapshot.healthy is True


def test_tool_health_opens_circuit_after_repeated_failures() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "boom", "Failing operation", {"type": "object", "properties": {}, "required": []},
        "low", lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    ))
    from nexus.core.tool_execution import ToolHealthRegistry

    health = ToolHealthRegistry(failure_threshold=2, cooldown_seconds=60)
    executor = ToolExecutor(registry=registry, health_registry=health)
    task = Task(objective="boom")

    assert executor.execute(task, "boom", {}).success is False
    assert executor.execute(task, "boom", {}).success is False
    blocked = executor.execute(task, "boom", {})
    assert blocked.success is False
    assert blocked.permission.value == "deny"
    assert "temporarily unavailable" in blocked.error
    snapshot = executor.health("boom")
    assert snapshot.failures == 2
    assert snapshot.consecutive_failures == 2
    assert snapshot.healthy is False


def test_tool_health_resets_after_success() -> None:
    registry = ToolRegistry()
    calls = {"count": 0}

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary")
        return "ok"

    registry.register(ToolSpec(
        "flaky", "Flaky operation", {"type": "object", "properties": {}, "required": []},
        "low", flaky,
    ))
    from nexus.core.tool_execution import ToolHealthRegistry

    health = ToolHealthRegistry(failure_threshold=3, cooldown_seconds=60)
    executor = ToolExecutor(registry=registry, health_registry=health)
    task = Task(objective="flaky")

    assert executor.execute(task, "flaky", {}).success is False
    assert executor.execute(task, "flaky", {}).success is True
    snapshot = executor.health("flaky")
    assert snapshot.successes == 1
    assert snapshot.failures == 1
    assert snapshot.consecutive_failures == 0
    assert snapshot.healthy is True
