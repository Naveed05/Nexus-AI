from __future__ import annotations

from dataclasses import dataclass

from .control_ledger import ControlEvent, ControlLedger


@dataclass(frozen=True)
class ControlAuditSnapshot:
    """Stable read-only audit snapshot suitable for APIs and operator views."""

    event_count: int
    head_sequence: int
    head_hash: str
    verified: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "event_count": self.event_count,
            "head_sequence": self.head_sequence,
            "head_hash": self.head_hash,
            "verified": self.verified,
        }


def snapshot(ledger: ControlLedger) -> ControlAuditSnapshot:
    """Return ledger health metadata without exposing mutable storage state."""
    events = ledger.load()
    head = events[-1] if events else None
    return ControlAuditSnapshot(
        event_count=len(events),
        head_sequence=head.sequence if head else 0,
        head_hash=head.event_hash if head else "",
        verified=True,
    )


def query(
    ledger: ControlLedger,
    *,
    action: str | None = None,
    actor: str | None = None,
    decision: str | None = None,
    limit: int | None = None,
) -> tuple[ControlEvent, ...]:
    """Expose deterministic, validated audit filtering through a small API boundary."""
    return ledger.audit(action=action, actor=actor, decision=decision, limit=limit)
