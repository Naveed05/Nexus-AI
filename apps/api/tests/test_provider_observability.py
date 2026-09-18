import pytest

from nexus.core.provider_failures import ProviderFailureKind, classify_provider_failure
from nexus.core.provider_telemetry import ProviderTelemetry, ProviderTelemetryEvent


class RateLimitError(Exception):
    pass


class StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"status {status_code}")


def test_classifies_transient_failures_as_retryable() -> None:
    failure = classify_provider_failure(TimeoutError("timed out"), provider="openai")
    assert failure.kind is ProviderFailureKind.TRANSIENT
    assert failure.retryable is True
    assert failure.provider == "openai"


def test_classifies_rate_limits_as_retryable() -> None:
    failure = classify_provider_failure(RateLimitError("rate limit exceeded"), provider="openai")
    assert failure.kind is ProviderFailureKind.RATE_LIMITED
    assert failure.retryable is True


def test_classifies_auth_and_invalid_request_as_non_retryable() -> None:
    assert classify_provider_failure(StatusError(401)).retryable is False
    assert classify_provider_failure(StatusError(422)).kind is ProviderFailureKind.INVALID_REQUEST


def test_telemetry_snapshot_aggregates_provider_attempts() -> None:
    telemetry = ProviderTelemetry()
    telemetry.record(ProviderTelemetryEvent("openai", "gpt-test", True, 10.0))
    telemetry.record(ProviderTelemetryEvent("openai", "gpt-fallback", False, 30.0, "rate_limited", 1))
    snapshot = telemetry.snapshot()
    assert snapshot["total_requests"] == 2
    assert snapshot["successes"] == 1
    assert snapshot["failures"] == 1
    assert snapshot["success_rate"] == 0.5
    assert snapshot["average_duration_ms"] == 20.0
    assert snapshot["providers"] == ("openai",)


def test_telemetry_rejects_invalid_event_values() -> None:
    with pytest.raises(ValueError, match="duration_ms"):
        ProviderTelemetryEvent("openai", "gpt-test", True, -1)
