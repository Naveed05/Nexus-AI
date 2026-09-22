from pathlib import Path

from nexus.core.collaboration_audit import CollaborationAuditLog


def test_audit_log_builds_and_verifies_hash_chain():
    log = CollaborationAuditLog()
    first = log.append("plan_created", "supervisor", {"workstreams": 2})
    second = log.append("conflict_resolved", "supervisor", {"resolution": "accept"})
    assert first.sequence == 1
    assert second.previous_hash == first.event_hash
    assert log.verify() == (True, None)


def test_audit_log_persists_across_instances(tmp_path: Path):
    path = str(tmp_path / "audit.sqlite3")
    first = CollaborationAuditLog(path)
    event = first.append("plan_created", "supervisor", {"objective": "demo"})
    second = CollaborationAuditLog(path)
    assert second.list() == (event,)
    assert second.verify() == (True, None)


def test_audit_log_is_bounded():
    log = CollaborationAuditLog(max_events=1)
    log.append("plan_created", "supervisor", {})
    try:
        log.append("second", "supervisor", {})
    except ValueError as exc:
        assert "capacity" in str(exc)
    else:
        raise AssertionError("expected bounded audit log to reject overflow")


def test_audit_log_rejects_empty_identity():
    log = CollaborationAuditLog()
    try:
        log.append("", "supervisor", {})
    except ValueError as exc:
        assert "event_type" in str(exc)
    else:
        raise AssertionError("expected empty event type to fail")


def test_audit_log_detects_tampering(tmp_path: Path):
    path = str(tmp_path / "audit.sqlite3")
    log = CollaborationAuditLog(path)
    log.append("plan_created", "supervisor", {"objective": "demo"})
    import sqlite3
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE collaboration_audit SET payload = ? WHERE sequence = 1", ('{"objective":"tampered"}',))
        conn.commit()
    assert log.verify()[0] is False


def test_audit_log_supports_filtered_cursor_queries(tmp_path: Path):
    log = CollaborationAuditLog(str(tmp_path / "audit.sqlite3"))
    log.append("plan_created", "supervisor", {"n": 1})
    log.append("conflict_resolved", "supervisor", {"n": 2})
    log.append("plan_created", "reviewer", {"n": 3})

    assert [event.sequence for event in log.list(event_type="plan_created")] == [1, 3]
    assert [event.sequence for event in log.list(actor="supervisor")] == [1, 2]
    assert [event.sequence for event in log.list(before_sequence=3)] == [1, 2]
    assert [event.sequence for event in log.list(limit=1)] == [3]


def test_audit_log_rejects_invalid_query_bounds():
    log = CollaborationAuditLog()
    try:
        log.list(before_sequence=0)
    except ValueError as exc:
        assert "before_sequence" in str(exc)
    else:
        raise AssertionError("expected invalid cursor to fail")


def test_audit_log_reports_operational_stats():
    log = CollaborationAuditLog(max_events=4)
    log.append("plan_created", "supervisor", {})
    stats = log.stats()
    assert stats["event_count"] == 1
    assert stats["capacity"] == 4
    assert stats["head_sequence"] == 1
    assert stats["latest_created_at"]
