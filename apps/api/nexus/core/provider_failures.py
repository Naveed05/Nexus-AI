from dataclasses import dataclass
from enum import Enum
from typing import Any


class ProviderFailureKind(str, Enum):
    """Normalized provider failure classes used by routing and fallback."""
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderFailure:
    kind: ProviderFailureKind
    retryable: bool
    provider: str | None = None
    status_code: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "retryable": self.retryable,
            "provider": self.provider,
            "status_code": self.status_code,
        }


def classify_provider_failure(exc: BaseException, *, provider: str | None = None) -> ProviderFailure:
    """Classify common provider errors without depending on a vendor SDK."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, bool) or (status is not None and not isinstance(status, int)):
        status = None
    name = type(exc).__name__.lower()
    message = str(exc).lower()

    if status == 429 or "rate limit" in message or "ratelimit" in name:
        return ProviderFailure(ProviderFailureKind.RATE_LIMITED, True, provider, status)
    if status in {401, 403} or "authentication" in message or "unauthorized" in message:
        return ProviderFailure(ProviderFailureKind.AUTHENTICATION, False, provider, status)
    if status in {400, 404, 422} or "invalid request" in message or "bad request" in message:
        return ProviderFailure(ProviderFailureKind.INVALID_REQUEST, False, provider, status)
    if status in {408, 409, 500, 502, 503, 504} or isinstance(exc, (TimeoutError, ConnectionError)):
        kind = ProviderFailureKind.UNAVAILABLE if status in {502, 503, 504} else ProviderFailureKind.TRANSIENT
        return ProviderFailure(kind, True, provider, status)
    if "timeout" in name or "temporarily unavailable" in message or "service unavailable" in message:
        return ProviderFailure(ProviderFailureKind.TRANSIENT, True, provider, status)
    return ProviderFailure(ProviderFailureKind.UNKNOWN, False, provider, status)
