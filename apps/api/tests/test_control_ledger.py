import json
from datetime import datetime, timezone

import pytest

from nexus.core.control_ledger import ControlLedger
from nexus.core.developer_approval import DeveloperApproval
from nexus.core.human_control import HumanControlPolicy


def test_ledger_appends_and_preserves_hash_chain(tmp_path):
    ledger = ControlLedger(tmp_path / "controls.json")
    first = ledger.append("file_write", "alice", "approved", "reviewed")
    second = ledger.append("production_deploy", "alice", "rejected", "not ready")
    events = ledger.load()
    assert len(events) == 2
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.event_hash
    assert all(event.verify() for event in events)


def test_ledger_round_trips_across_instances(tmp_path):
    path = tmp_path / "controls.json"
    first = ControlLedger(path)
    event = first.append("account_change", "reviewer", "approved", "verified")
    restored = ControlLedger(path).load()
    assert restored == (event,)


def test_typed_control_decision_is_normalized_into_ledger(tmp_path):
    decision = HumanControlPolicy().evaluate("production_deploy", approved=True)
    event = ControlLedger(tmp_path / "controls.json").append_decision(decision, actor="reviewer")
    assert event.action == "production_deploy"
    assert event.actor == "reviewer"
    assert event.decision == "allowed"
    assert "explicit human approval" in event.reason


def test_approval_provenance_binds_exact_patch_fingerprint(tmp_path):
    fingerprint = "a" * 64
    approval = DeveloperApproval.decide(
        fingerprint,
        approved=True,
        actor="reviewer",
        reason="reviewed exact patch",
        decided_at=datetime.now(timezone.utc).isoformat(),
    )
    event = ControlLedger(tmp_path / "controls.json").append_approval(approval)
    assert event.action == "patch_execution"
    assert event.actor == "reviewer"
    assert event.decision == "approved"
    assert f"patch_fingerprint={fingerprint}" in event.reason
    assert "reviewed exact patch" in event.reason


def test_approval_provenance_preserves_rejection_and_pending_state(tmp_path):
    path = tmp_path / "controls.json"
    fingerprint = "b" * 64
    pending = DeveloperApproval.pending(fingerprint, actor="reviewer")
    rejected = DeveloperApproval.decide(fingerprint, approved=False, actor="reviewer", reason="unsafe")
    ledger = ControlLedger(path)
    first = ledger.append_approval(pending)
    second = ledger.append_approval(rejected, expected_head_hash=first.event_hash)
    assert first.decision == "pending"
    assert second.decision == "rejected"
    assert second.previous_hash == first.event_hash


def test_ledger_rejects_stale_expected_head(tmp_path):
    path = tmp_path / "controls.json"
    first = ControlLedger(path)
    event = first.append("file_write", "alice", "approved", "reviewed")
    second = ControlLedger(path)
    second.append("database_write", "bob", "approved", "reviewed")
    with pytest.raises(RuntimeError, match="head changed"):
        first.append("production_deploy", "alice", "approved", "reviewed", expected_head_hash=event.event_hash)


def test_ledger_accepts_matching_expected_head(tmp_path):
    path = tmp_path / "controls.json"
    ledger = ControlLedger(path)
    first = ledger.append("file_write", "alice", "approved", "reviewed")
    second = ledger.append("database_write", "alice", "approved", "reviewed", expected_head_hash=first.event_hash)
    assert second.previous_hash == first.event_hash
    assert ledger.verify() is True


def test_ledger_detects_event_tampering(tmp_path):
    path = tmp_path / "controls.json"
    ledger = ControlLedger(path)
    ledger.append("file_write", "alice", "approved", "reviewed")
    payload = json.loads(path.read_text())
    payload["events"][0]["reason"] = "tampered"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="integrity check failed"):
        ledger.load()


def test_ledger_detects_chain_reordering(tmp_path):
    path = tmp_path / "controls.json"
    ledger = ControlLedger(path)
    ledger.append("file_write", "alice", "approved", "reviewed")
    ledger.append("database_write", "alice", "approved", "reviewed")
    payload = json.loads(path.read_text())
    payload["events"].reverse()
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="integrity check failed"):
        ledger.load()


def test_ledger_rejects_unsupported_schema(tmp_path):
    path = tmp_path / "controls.json"
    path.write_text(json.dumps({"schema": "old", "events": []}))
    with pytest.raises(ValueError, match="unsupported human control ledger schema"):
        ControlLedger(path).load()


def test_ledger_rejects_invalid_event_fields(tmp_path):
    path = tmp_path / "controls.json"
    path.write_text(json.dumps({"schema": "nexus-human-control-ledger-v1", "events": [{"sequence": 1}]}))
    with pytest.raises(ValueError, match="invalid human control ledger event"):
        ControlLedger(path).load()
