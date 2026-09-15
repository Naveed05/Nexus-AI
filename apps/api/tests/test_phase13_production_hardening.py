import pytest

from nexus.core.rate_limiter import InMemoryRateLimiter
from nexus.core.security_policy import SecurityPolicy


def test_security_policy_accepts_normal_request_and_rejects_unsafe_forwarding():
    policy = SecurityPolicy()

    allowed = policy.evaluate(method="GET", path="/api/health", headers={"accept": "application/json"})
    blocked = policy.evaluate(method="GET", path="/api/health", headers={"X-Forwarded-Host": "attacker.example"})

    assert allowed.allowed is True
    assert blocked.allowed is False
    assert "unsafe_forwarding_header" in blocked.violations


def test_security_policy_rejects_invalid_and_oversized_paths():
    policy = SecurityPolicy()
    assert policy.evaluate(method="GET", path="health").allowed is False
    assert policy.evaluate(method="GET", path="/" + "x" * 2048).allowed is False


def test_rate_limiter_enforces_window_and_reports_retry():
    limiter = InMemoryRateLimiter(limit=2, window_seconds=10)

    assert limiter.allow("user-1", now=100).remaining == 1
    assert limiter.allow("user-1", now=101).remaining == 0
    blocked = limiter.allow("user-1", now=102)

    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 8.0
    assert limiter.allow("user-2", now=102).allowed is True


def test_rate_limiter_expires_old_requests_and_validates_configuration():
    limiter = InMemoryRateLimiter(limit=1, window_seconds=5)
    assert limiter.allow("user-1", now=10).allowed is True
    assert limiter.allow("user-1", now=15).allowed is True

    with pytest.raises(ValueError):
        InMemoryRateLimiter(limit=0)
    with pytest.raises(ValueError):
        InMemoryRateLimiter(window_seconds=0)
    with pytest.raises(ValueError):
        limiter.allow("", now=20)
