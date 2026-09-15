from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: float = 0.0


class InMemoryRateLimiter:
    """Small deterministic rate limiter suitable for a single API process."""

    def __init__(self, limit: int = 60, window_seconds: float = 60.0) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def allow(self, key: str, *, now: float | None = None) -> RateLimitResult:
        if not key.strip():
            raise ValueError("key must not be empty")
        current = monotonic() if now is None else now
        timestamps = [t for t in self._requests.get(key, []) if current - t < self.window_seconds]
        if len(timestamps) >= self.limit:
            retry_after = max(0.0, self.window_seconds - (current - timestamps[0]))
            self._requests[key] = timestamps
            return RateLimitResult(False, 0, round(retry_after, 3))
        timestamps.append(current)
        self._requests[key] = timestamps
        return RateLimitResult(True, self.limit - len(timestamps))

    def reset(self, key: str) -> None:
        self._requests.pop(key, None)
