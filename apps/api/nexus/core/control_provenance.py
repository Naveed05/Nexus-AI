from __future__ import annotations

from dataclasses import dataclass

from .control_ledger import ControlEvent, ControlLedger
from .developer_approval import DeveloperApproval


@dataclass(frozen=True)
class PatchExecutionProvenance:
    """Immutable linkage between one approval event and one execution event."""

    patch_fingerprint: str
    approval_event_hash: str
    execution_event_hash: str

    def verify(self, ledger: ControlLedger) -> bool:
        events = ledger.load()
        by_hash = {event.event_hash: event for event in events}
        approval = by_hash.get(self.approval_event_hash)
        execution = by_hash.get(self.execution_event_hash)
        if approval is None or execution is None:
            return False
        if execution.previous_hash != approval.event_hash:
            return False
        return (
            approval.decision == "approved"
            and f"patch_fingerprint={self.patch_fingerprint}" in approval.reason
            and execution.decision == "executed"
            and f"executed_patch_fingerprint={self.patch_fingerprint}" in execution.reason
            and f"approval_event={approval.event_hash}" in execution.reason
        )


def record_approved_patch_execution(
    ledger: ControlLedger,
    approval: DeveloperApproval,
    *,
    patch_fingerprint: str,
    actor: str,
    expected_head_hash: str | None = None,
) -> PatchExecutionProvenance:
    """Atomically sequence approval and execution provenance through the ledger API.

    The approval must target the exact patch. Execution is then permitted only from
    that approval event while it remains the current ledger head.
    """
    if not approval.is_approved:
        raise ValueError("execution requires an approved decision")
    if not approval.matches(patch_fingerprint):
        raise ValueError("approval patch fingerprint does not match executed artifact")
    approval_event = ledger.append_approval(
        approval,
        expected_head_hash=expected_head_hash,
        expected_patch_fingerprint=patch_fingerprint,
    )
    execution_event = ledger.append_execution(
        approval,
        patch_fingerprint=patch_fingerprint,
        actor=actor,
        approval_event_hash=approval_event.event_hash,
    )
    provenance = PatchExecutionProvenance(
        patch_fingerprint=patch_fingerprint,
        approval_event_hash=approval_event.event_hash,
        execution_event_hash=execution_event.event_hash,
    )
    if not provenance.verify(ledger):
        raise RuntimeError("patch execution provenance verification failed")
    return provenance


def verify_patch_execution_provenance(
    ledger: ControlLedger, provenance: PatchExecutionProvenance
) -> bool:
    """Fail closed when approval and execution provenance no longer match."""
    return provenance.verify(ledger)
