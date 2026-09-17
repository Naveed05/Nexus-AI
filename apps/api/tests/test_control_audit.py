import pytest

from nexus.core.control_audit import query, snapshot
from nexus.core.control_ledger import ControlLedger


def test_snapshot_reports_verified_head(tmp_path):
    ledger = ControlLedger(tmp_path / "controls.json")
    first = ledger.append("file_write", "alice", "allowed", "reviewed")
    second = ledger.append("production_deploy", "bob", "denied", "approval required")
    result = snapshot(ledger)
    assert result.event_count == 2
    assert result.head_sequence == 2
    assert result.head_hash == second.event_hash
    assert result.head_hash != first.event_hash
    assert result.verified is True


def test_query_filters_newest_first_and_is_bounded(tmp_path):
    ledger = ControlLedger(tmp_path / "controls.json")
    ledger.append("file_write", "alice", "allowed", "one")
    ledger.append("file_write", "bob", "denied", "two")
    ledger.append("file_write", "alice", "allowed", "three")
    result = query(ledger, action="FILE_WRITE", actor="alice", decision="ALLOWED", limit=1)
    assert len(result) == 1
    assert result[0].reason == "three"


def test_query_rejects_invalid_limit(tmp_path):
    ledger = ControlLedger(tmp_path / "controls.json")
    with pytest.raises(ValueError, match="limit must be at least 1"):
        query(ledger, limit=0)


def test_query_fails_closed_on_tampered_ledger(tmp_path):
    ledger = ControlLedger(tmp_path / "controls.json")
    ledger.append("file_write", "alice", "allowed", "reviewed")
    payload = ledger._path.read_text(encoding="utf-8").replace("reviewed", "tampered")
    ledger._path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="integrity check failed"):
        query(ledger)
