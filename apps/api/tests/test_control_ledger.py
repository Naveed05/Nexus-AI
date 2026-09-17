import json

import pytest

from nexus.core.control_ledger import ControlLedger


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
