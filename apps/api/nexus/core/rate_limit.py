from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimitExceeded(Exception):
    pass


class SlidingWindowRateLimiter:
    """Small bounded in-process limiter for the single-instance beta boundary."""

    def __init__(self, limit: int = 120, window_seconds: int = 60, max_clients: int = 10_000) -> None:
        if limit < 1 or window_seconds < 1 or max_clients < 1:
            raise ValueError("rate limiter parameters must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, client_id: str, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            if client_id not in self._events and len(self._events) >= self.max_clients:
                oldest = min(self._events, key=lambda key: self._events[key][-1] if self._events[key] else float("inf"))
                self._events.pop(oldest, None)
            bucket = self._events[client_id]
            cutoff = timestamp - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                raise RateLimitExceeded("rate limit exceeded")
            bucket.append(timestamp)
