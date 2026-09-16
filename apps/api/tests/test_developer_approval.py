from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from nexus.core.developer_approval import ApprovalStatus, DeveloperApproval


FINGERPRINT = "a" * 64
TIMESTAMP = "2026-09-16T18:00:00+00:00"


def test_pending_approval_exposes_explicit_lifecycle_state() -> None:
    approval = DeveloperApproval.pending(FINGERPRINT)

    assert approval.status is ApprovalStatus.PENDING
    assert approval.is_approved is False
    assert approval.is_pending is True
    assert approval.is_decided is False
    assert approval.matches(FINGERPRINT) is True
    assert approval.matches("b" * 64) is False


def test_approved_decision_requires_actor_reason_and_serializes() -> None:
    approval = DeveloperApproval.decide(
        FINGERPRINT,
        approved=True,
        actor="human-reviewer",
        reason="Reviewed the bounded patch.",
        decided_at=TIMESTAMP,
    )

    assert approval.status is ApprovalStatus.APPROVED
    assert approval.is_approved is True
    assert approval.is_pending is False
    assert approval.is_decided is True
    assert approval.as_dict() == {
        "patch_fingerprint": FINGERPRINT,
        "status": "approved",
        "actor": "human-reviewer",
        "reason": "Reviewed the bounded patch.",
        "decided_at": TIMESTAMP,
        "is_approved": True,
        "is_pending": False,
        "is_decided": True,
    }


def test_rejected_decision_is_explicit() -> None:
    approval = DeveloperApproval.decide(
        FINGERPRINT,
        approved=False,
        actor="human-reviewer",
        reason="Patch exceeds the intended change scope.",
        decided_at=TIMESTAMP,
    )

    assert approval.status is ApprovalStatus.REJECTED
    assert approval.is_approved is False
    assert approval.is_pending is False
    assert approval.is_decided is True


def test_decision_is_immutable() -> None:
    approval = DeveloperApproval.pending(FINGERPRINT)

    with pytest.raises(FrozenInstanceError):
        approval.status = ApprovalStatus.APPROVED  # type: ignore[misc]


def test_decision_rejects_invalid_identity_and_timestamp() -> None:
    with pytest.raises(ValueError, match="patch_fingerprint"):
        DeveloperApproval("", ApprovalStatus.PENDING, "system", "", TIMESTAMP)

    with pytest.raises(ValueError, match="patch_fingerprint"):
        DeveloperApproval("A" * 64, ApprovalStatus.PENDING, "system", "", TIMESTAMP)

    with pytest.raises(ValueError, match="patch_fingerprint"):
        DeveloperApproval("short", ApprovalStatus.PENDING, "system", "", TIMESTAMP)

    with pytest.raises(ValueError, match="actor"):
        DeveloperApproval(FINGERPRINT, ApprovalStatus.PENDING, "", "", TIMESTAMP)

    with pytest.raises(ValueError, match="reason"):
        DeveloperApproval(FINGERPRINT, ApprovalStatus.APPROVED, "reviewer", "", TIMESTAMP)

    with pytest.raises(ValueError, match="ISO-8601"):
        DeveloperApproval(FINGERPRINT, ApprovalStatus.PENDING, "system", "", "not-a-date")

    with pytest.raises(ValueError, match="timezone"):
        DeveloperApproval(FINGERPRINT, ApprovalStatus.PENDING, "system", "", "2026-09-16T18:00:00")


def test_approval_timestamp_accepts_small_clock_skew() -> None:
    approval = DeveloperApproval.decide(
        FINGERPRINT,
        approved=True,
        actor="reviewer",
        reason="Reviewed the exact patch.",
        decided_at="2026-09-16T18:00:20+00:00",
    )
    now = datetime(2026, 9, 16, 18, 0, 0, tzinfo=timezone.utc)

    assert approval.is_time_valid(now=now, max_future_seconds=30) is True
    assert approval.is_time_valid(now=now, max_future_seconds=10) is False


def test_approval_timestamp_rejects_invalid_clock_arguments() -> None:
    approval = DeveloperApproval.pending(FINGERPRINT)
    with pytest.raises(ValueError, match="max_future_seconds"):
        approval.is_time_valid(max_future_seconds=-1)
    with pytest.raises(ValueError, match="timezone"):
        approval.is_time_valid(now=datetime(2026, 9, 16, 18, 0, 0))
