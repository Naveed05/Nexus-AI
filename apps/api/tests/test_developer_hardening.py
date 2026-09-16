from datetime import datetime, timezone

import pytest

from nexus.core.developer_approval import DeveloperApproval
from nexus.core.developer_policy import DeveloperPolicy, PatchRisk


FINGERPRINT = "a" * 64


def test_approval_freshness_window_is_enforced() -> None:
    approval = DeveloperApproval.decide(
        FINGERPRINT,
        approved=True,
        actor="reviewer",
        reason="Reviewed the exact patch.",
        decided_at="2026-09-16T17:30:00+00:00",
    )
    now = datetime(2026, 9, 16, 18, 0, 0, tzinfo=timezone.utc)
    assert approval.is_fresh(now=now, max_age_seconds=1800) is True
    assert approval.is_fresh(now=now, max_age_seconds=1799) is False


def test_approval_freshness_rejects_future_and_invalid_clock() -> None:
    future = DeveloperApproval.decide(
        FINGERPRINT,
        approved=True,
        actor="reviewer",
        reason="Reviewed.",
        decided_at="2026-09-16T18:00:01+00:00",
    )
    now = datetime(2026, 9, 16, 18, 0, 0, tzinfo=timezone.utc)
    assert future.is_fresh(now=now, max_age_seconds=3600) is False
    with pytest.raises(ValueError, match="max_age_seconds"):
        future.is_fresh(max_age_seconds=-1)
    with pytest.raises(ValueError, match="timezone"):
        future.is_fresh(now=datetime(2026, 9, 16, 18, 0, 0))


def test_high_confidence_secret_patterns_are_blocked() -> None:
    policy = DeveloperPolicy()
    cases = (
        'api_key = "this-is-a-long-secret-value-12345"',
        'token: "this-is-a-long-secret-value-12345"',
        "-----BEGIN RSA PRIVATE KEY-----",
        "AKIA1234567890ABCDEF",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
    )
    for secret in cases:
        decision = policy.evaluate(("src/service.py",), additions=1, added_content=f"+{secret}\n")
        assert decision.risk is PatchRisk.BLOCKED
        assert decision.allowed is False
        assert "secret material" in decision.reasons[0]


def test_secret_scanner_ignores_unrelated_normal_content() -> None:
    decision = DeveloperPolicy().evaluate(
        ("src/service.py",),
        additions=2,
        added_content='+message = "hello world"\n+api_key_name = "public_identifier"\n',
    )
    assert decision.allowed is True
    assert decision.risk is PatchRisk.LOW
