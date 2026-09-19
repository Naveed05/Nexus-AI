from datetime import datetime, timedelta, timezone

import pytest

from nexus.core.approvals import ApprovalError, issue_approval
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


def test_authorize_requires_valid_approval_for_medium_tool() -> None:
    policy = PermissionPolicy()
    tool = make_tool(risk_level="medium")
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    arguments = {"request": "approved"}

    assert (
        policy.authorize(tool, RiskLevel.MEDIUM, arguments=arguments)
        == PermissionDecision.APPROVAL_REQUIRED
    )

    approval = issue_approval(
        approver="naveed",
        tool_name=tool.name,
        arguments=arguments,
        now=now,
    )
    assert (
        policy.authorize(
            tool,
            RiskLevel.MEDIUM,
            arguments=arguments,
            approval=approval,
            now=now + timedelta(seconds=5),
        )
        == PermissionDecision.ALLOW
    )


def test_authorize_rejects_stale_or_mismatched_approval() -> None:
    policy = PermissionPolicy()
    tool = make_tool(risk_level="high", permission="high_risk")
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    approval = issue_approval(
        approver="naveed",
        tool_name=tool.name,
        arguments={"request": "approved"},
        ttl_seconds=30,
        now=now,
    )

    with pytest.raises(ApprovalError, match="fingerprint"):
        policy.authorize(
            tool,
            RiskLevel.HIGH,
            arguments={"request": "changed"},
            approval=approval,
            now=now + timedelta(seconds=5),
        )

    with pytest.raises(ApprovalError, match="expired"):
        policy.authorize(
            tool,
            RiskLevel.HIGH,
            arguments={"request": "approved"},
            approval=approval,
            now=now + timedelta(seconds=30),
        )
