from nexus.core.collaboration_audit import CollaborationAuditLog


def test_audit_log_builds_and_verifies_hash_chain():
    log = CollaborationAuditLog()
    first = log.append("plan_created", "supervisor", {"workstreams": 2})
    second = log.append("conflict_resolved", "supervisor", {"resolution": "accept"})
    assert first.sequence == 1
    assert second.previous_hash == first.event_hash
    assert log.verify() == (True, None)


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
