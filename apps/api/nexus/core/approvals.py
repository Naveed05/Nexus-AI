"""Approval and provenance primitives for privileged NEXUS actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from secrets import token_urlsafe


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def action_fingerprint(*, tool_name: str, arguments: dict[str, object]) -> str:
    """Return a stable digest for the exact tool action a user approves."""
    payload = json.dumps(
        {"tool": tool_name, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Approval:
    approval_id: str
    approver: str
    fingerprint: str
    issued_at: datetime
    expires_at: datetime


class ApprovalError(ValueError):
    """Raised when an approval cannot authorize the requested action."""


def issue_approval(
    *,
    approver: str,
    tool_name: str,
    arguments: dict[str, object],
    ttl_seconds: int = 300,
    now: datetime | None = None,
) -> Approval:
    if not approver.strip():
        raise ValueError("approver cannot be empty")
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be greater than zero")

    issued_at = now or _utc_now()
    if issued_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    return Approval(
        approval_id=token_urlsafe(18),
        approver=approver.strip(),
        fingerprint=action_fingerprint(tool_name=tool_name, arguments=arguments),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
    )


def validate_approval(
    approval: Approval,
    *,
    tool_name: str,
    arguments: dict[str, object],
    now: datetime | None = None,
    expected_approver: str | None = None,
) -> None:
    """Validate identity, exact action binding, and approval freshness."""
    current = now or _utc_now()
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not approval.approver.strip():
        raise ApprovalError("approval has no approver")
    if expected_approver is not None and approval.approver != expected_approver.strip():
        raise ApprovalError("approval approver does not match the execution actor")
    if current < approval.issued_at:
        raise ApprovalError("approval is not yet valid")
    if current >= approval.expires_at:
        raise ApprovalError("approval has expired")

    expected = action_fingerprint(tool_name=tool_name, arguments=arguments)
    if expected != approval.fingerprint:
        raise ApprovalError("approval fingerprint does not match the requested action")
