import pytest

from nexus.core.task import Task
from nexus.core.tool_execution import ToolExecutor
from nexus.core.tools import ToolSpec, ToolRegistry


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


def test_tool_executor_requires_approval_for_medium_risk() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "risky", "Risky operation", {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False,
        }, "medium", lambda: "ok",
    ))
    executor = ToolExecutor(registry=registry)
    task = Task(objective="risky")
    blocked = executor.execute(task, "risky", {})
    assert blocked.success is False
    assert blocked.permission.value == "approval_required"
    allowed = executor.execute(task, "risky", {}, approved=True)
    assert allowed.success is True


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
