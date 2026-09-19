from datetime import datetime, timedelta, timezone

import pytest

from nexus.core.approvals import (
    ApprovalError,
    action_fingerprint,
    issue_approval,
    validate_approval,
)


def test_action_fingerprint_is_deterministic_and_order_independent() -> None:
    first = action_fingerprint(tool_name="delete_file", arguments={"path": "a", "force": True})
    second = action_fingerprint(tool_name="delete_file", arguments={"force": True, "path": "a"})
    assert first == second


def test_approval_is_bound_to_exact_action() -> None:
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    approval = issue_approval(
        approver="naveed",
        tool_name="delete_file",
        arguments={"path": "a"},
        now=now,
    )

    validate_approval(
        approval,
        tool_name="delete_file",
        arguments={"path": "a"},
        now=now + timedelta(seconds=30),
    )

    with pytest.raises(ApprovalError, match="fingerprint"):
        validate_approval(
            approval,
            tool_name="delete_file",
            arguments={"path": "b"},
            now=now + timedelta(seconds=30),
        )


def test_expired_approval_is_rejected() -> None:
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    approval = issue_approval(
        approver="naveed",
        tool_name="modify_workspace",
        arguments={"workspace": "demo"},
        ttl_seconds=60,
        now=now,
    )

    with pytest.raises(ApprovalError, match="expired"):
        validate_approval(
            approval,
            tool_name="modify_workspace",
            arguments={"workspace": "demo"},
            now=now + timedelta(seconds=60),
        )


def test_approval_requires_timezone_aware_time() -> None:
    naive = datetime(2026, 9, 19, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        issue_approval(
            approver="naveed",
            tool_name="modify_workspace",
            arguments={},
            now=naive,
        )


def test_approval_rejects_future_issue_time() -> None:
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    approval = issue_approval(
        approver="naveed",
        tool_name="modify_workspace",
        arguments={},
        now=now + timedelta(seconds=10),
    )

    with pytest.raises(ApprovalError, match="not yet valid"):
        validate_approval(approval, tool_name="modify_workspace", arguments={}, now=now)
