import pytest

from nexus.core.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter


def test_rate_limiter_allows_up_to_limit() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
    limiter.check("user", now=100)
    limiter.check("user", now=101)
    with pytest.raises(RateLimitExceeded):
        limiter.check("user", now=102)


def test_rate_limiter_expires_old_events() -> None:
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
    limiter.check("user", now=100)
    limiter.check("user", now=161)
