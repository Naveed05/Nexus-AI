from datetime import datetime, timezone

import pytest

from nexus.core.control_ledger import ControlLedger
from nexus.core.control_provenance import (
    PatchExecutionProvenance,
    record_approved_patch_execution,
    verify_patch_execution_provenance,
)
from nexus.core.developer_approval import DeveloperApproval


def _approval(fingerprint: str) -> DeveloperApproval:
    return DeveloperApproval.decide(
        fingerprint,
        approved=True,
        actor="reviewer",
        reason="approved exact patch",
        decided_at=datetime.now(timezone.utc).isoformat(),
    )


def test_recorded_execution_is_directly_chained_to_approval(tmp_path):
    fingerprint = "a" * 64
    ledger = ControlLedger(tmp_path / "controls.json")
    provenance = record_approved_patch_execution(
        ledger, _approval(fingerprint), patch_fingerprint=fingerprint, actor="executor"
    )
    events = ledger.load()
    assert len(events) == 2
    assert events[1].previous_hash == events[0].event_hash
    assert provenance.verify(ledger)
    assert verify_patch_execution_provenance(ledger, provenance)


def test_provenance_rejects_mismatched_patch(tmp_path):
    fingerprint = "b" * 64
    ledger = ControlLedger(tmp_path / "controls.json")
    with pytest.raises(ValueError, match="does not match"):
        record_approved_patch_execution(
            ledger,
            _approval(fingerprint),
            patch_fingerprint="c" * 64,
            actor="executor",
        )
    assert ledger.load() == ()


def test_provenance_fails_closed_after_tampering(tmp_path):
    fingerprint = "d" * 64
    ledger = ControlLedger(tmp_path / "controls.json")
    provenance = record_approved_patch_execution(
        ledger, _approval(fingerprint), patch_fingerprint=fingerprint, actor="executor"
    )
    assert provenance.verify(ledger)
    payload = ledger._path.read_text(encoding="utf-8").replace(
        f"executed_patch_fingerprint={fingerprint}",
        "executed_patch_fingerprint=" + "e" * 64,
    )
    ledger._path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="integrity check failed"):
        ledger.load()


def test_provenance_value_is_immutable(tmp_path):
    fingerprint = "f" * 64
    ledger = ControlLedger(tmp_path / "controls.json")
    provenance = record_approved_patch_execution(
        ledger, _approval(fingerprint), patch_fingerprint=fingerprint, actor="executor"
    )
    assert isinstance(provenance, PatchExecutionProvenance)
    with pytest.raises(AttributeError):
        provenance.patch_fingerprint = "0" * 64
