from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SecurityPolicyResult:
    allowed: bool
    reason: str
    violations: Tuple[str, ...] = ()


class SecurityPolicy:
    """Deterministic production safety checks for externally supplied requests."""

    _blocked_headers = {"x-forwarded-host", "x-original-url"}

    def evaluate(self, *, method: str, path: str, headers: dict[str, str] | None = None) -> SecurityPolicyResult:
        violations: list[str] = []
        normalized_method = method.strip().upper()
        normalized_path = path.strip()
        normalized_headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}

        if not normalized_method:
            violations.append("missing_method")
        if not normalized_path.startswith("/"):
            violations.append("invalid_path")
        if len(normalized_path) > 2048:
            violations.append("path_too_long")
        if any(header in normalized_headers for header in self._blocked_headers):
            violations.append("unsafe_forwarding_header")

        if violations:
            return SecurityPolicyResult(False, "Request violates production security policy.", tuple(violations))
        return SecurityPolicyResult(True, "Request satisfies production security policy.")
