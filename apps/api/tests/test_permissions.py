from nexus.core.permissions import PermissionDecision, PermissionPolicy
from nexus.core.task import RiskLevel
from nexus.core.tools import ToolSpec


def make_tool(*, risk_level: str = "low", permission: str = "read") -> ToolSpec:
    return ToolSpec(
        name=f"test_{risk_level}_{permission}",
        description="test tool",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        risk_level=risk_level,
        permission=permission,
        handler=lambda: {"ok": True},
    )


def test_low_read_tool_is_allowed_for_low_risk_task() -> None:
    decision = PermissionPolicy().decide(make_tool(), RiskLevel.LOW)
    assert decision == PermissionDecision.ALLOW


def test_medium_tool_requires_approval() -> None:
    decision = PermissionPolicy().decide(make_tool(risk_level="medium"), RiskLevel.MEDIUM)
    assert decision == PermissionDecision.APPROVAL_REQUIRED


def test_modify_tool_is_denied_for_low_risk_task() -> None:
    decision = PermissionPolicy().decide(
        make_tool(permission="modify"), RiskLevel.LOW
    )
    assert decision == PermissionDecision.DENY


def test_high_risk_tool_requires_approval_even_for_high_risk_task() -> None:
    decision = PermissionPolicy().decide(
        make_tool(risk_level="high", permission="high_risk"), RiskLevel.HIGH
    )
    assert decision == PermissionDecision.APPROVAL_REQUIRED
