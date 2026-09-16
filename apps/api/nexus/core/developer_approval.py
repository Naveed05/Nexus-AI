from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class DeveloperApproval:
    """Immutable human decision bound to one exact developer patch fingerprint."""

    patch_fingerprint: str
    status: ApprovalStatus
    actor: str
    reason: str
    decided_at: str

    def __post_init__(self) -> None:
        if not self.patch_fingerprint.strip():
            raise ValueError("patch_fingerprint must not be empty")
        if not self.actor.strip():
            raise ValueError("actor must not be empty")
        if self.status is not ApprovalStatus.PENDING and not self.reason.strip():
            raise ValueError("reason is required for a decided approval")
        try:
            datetime.fromisoformat(self.decided_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("decided_at must be an ISO-8601 timestamp") from exc

    @property
    def is_approved(self) -> bool:
        return self.status is ApprovalStatus.APPROVED

    def matches(self, patch_fingerprint: str) -> bool:
        """Return True only when this decision targets the exact patch artifact."""
        return bool(patch_fingerprint) and self.patch_fingerprint == patch_fingerprint

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "patch_fingerprint": self.patch_fingerprint,
            "status": self.status.value,
            "actor": self.actor,
            "reason": self.reason,
            "decided_at": self.decided_at,
            "is_approved": self.is_approved,
        }

    @classmethod
    def pending(cls, patch_fingerprint: str, actor: str = "system") -> "DeveloperApproval":
        return cls(
            patch_fingerprint=patch_fingerprint,
            status=ApprovalStatus.PENDING,
            actor=actor,
            reason="",
            decided_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def decide(
        cls,
        patch_fingerprint: str,
        *,
        approved: bool,
        actor: str,
        reason: str,
        decided_at: str | None = None,
    ) -> "DeveloperApproval":
        return cls(
            patch_fingerprint=patch_fingerprint,
            status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            actor=actor,
            reason=reason,
            decided_at=decided_at or datetime.now(timezone.utc).isoformat(),
        )
