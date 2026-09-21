from __future__ import annotations

from threading import Lock


class ServiceMetrics:
    """Bounded, dependency-free counters suitable for Prometheus scraping."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests = 0
        self._errors = 0

    def observe_request(self, status_code: int) -> None:
        with self._lock:
            self._requests += 1
            if status_code >= 500:
                self._errors += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"requests": self._requests, "errors": self._errors}

    def prometheus(self, service: str) -> str:
        data = self.snapshot()
        service = service.replace("\\", "\\\\").replace('"', '\\"')
        return (
            "# HELP nexus_http_requests_total Total HTTP requests observed.\n"
            "# TYPE nexus_http_requests_total counter\n"
            f'nexus_http_requests_total{{service="{service}"}} {data["requests"]}\n'
            "# HELP nexus_http_errors_total Total HTTP 5xx responses observed.\n"
            "# TYPE nexus_http_errors_total counter\n"
            f'nexus_http_errors_total{{service="{service}"}} {data["errors"]}\n'
        )


service_metrics = ServiceMetrics()
