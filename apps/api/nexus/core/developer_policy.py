from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
import re


class PatchRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class DeveloperPolicyDecision:
    """Deterministic authorization result for a proposed developer patch."""

    risk: PatchRisk
    allowed: bool
    requires_approval: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "risk": self.risk.value,
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "reasons": list(self.reasons),
        }


class DeveloperPolicy:
    """Bound the blast radius of AI-generated code changes before execution."""

    DEFAULT_SENSITIVE = (
        ".env",
        ".env.example",
        "credentials",
        "secrets",
        "secret",
        "id_rsa",
        ".pem",
        ".key",
        "settings.py",
    )
    _SECRET_PATTERNS = (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
        re.compile(r"\b(?:xoxb|xoxp)-[A-Za-z0-9-]{20,}\b"),
        re.compile(r"\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{20,}['\"]", re.IGNORECASE),
        re.compile(r"\btoken\s*[:=]\s*['\"][^'\"]{20,}['\"]", re.IGNORECASE),
    )

    def __init__(
        self,
        *,
        max_files: int = 8,
        max_changed_lines: int = 400,
        sensitive_fragments: tuple[str, ...] = DEFAULT_SENSITIVE,
    ) -> None:
        if max_files < 1:
            raise ValueError("max_files must be at least 1")
        if max_changed_lines < 1:
            raise ValueError("max_changed_lines must be at least 1")
        self.max_files = max_files
        self.max_changed_lines = max_changed_lines
        self.sensitive_fragments = tuple(item.lower() for item in sensitive_fragments if item)

    def evaluate(
        self,
        paths: tuple[str, ...],
        *,
        additions: int = 0,
        deletions: int = 0,
        approved: bool = False,
        added_content: str = "",
    ) -> DeveloperPolicyDecision:
        normalized = tuple(dict.fromkeys(paths))
        changed_lines = additions + deletions
        reasons: list[str] = []

        unsafe = [path for path in normalized if self._unsafe_path(path)]
        if unsafe:
            return DeveloperPolicyDecision(
                risk=PatchRisk.BLOCKED,
                allowed=False,
                requires_approval=False,
                reasons=(f"unsafe or sensitive path: {unsafe[0]}",),
            )

        secret_match = self._secret_like_content(added_content)
        if secret_match:
            return DeveloperPolicyDecision(
                risk=PatchRisk.BLOCKED,
                allowed=False,
                requires_approval=False,
                reasons=(f"high-confidence secret material detected in added content: {secret_match}",),
            )

        if len(normalized) > self.max_files:
            return DeveloperPolicyDecision(
                risk=PatchRisk.BLOCKED,
                allowed=False,
                requires_approval=False,
                reasons=(f"patch touches {len(normalized)} files; limit is {self.max_files}",),
            )

        if changed_lines > self.max_changed_lines:
            return DeveloperPolicyDecision(
                risk=PatchRisk.BLOCKED,
                allowed=False,
                requires_approval=False,
                reasons=(
                    f"patch changes {changed_lines} lines; limit is {self.max_changed_lines}",
                ),
            )

        if len(normalized) >= 5 or changed_lines >= 150:
            risk = PatchRisk.HIGH
            reasons.append("large patch requires explicit human approval")
            if not approved:
                return DeveloperPolicyDecision(risk, False, True, tuple(reasons))
        elif len(normalized) >= 3 or changed_lines >= 50:
            risk = PatchRisk.MEDIUM
            reasons.append("moderate patch size")
        else:
            risk = PatchRisk.LOW
            reasons.append("patch is within low-blast-radius limits")

        if approved:
            reasons.append("explicit approval supplied")
        return DeveloperPolicyDecision(risk, True, risk is PatchRisk.HIGH and not approved, tuple(reasons))

    def _secret_like_content(self, added_content: str) -> str | None:
        for line in added_content.splitlines():
            candidate = line[1:] if line.startswith("+") else line
            normalized = candidate.replace('\\"', '"').replace("\\'", "'")
            for pattern in self._SECRET_PATTERNS:
                if pattern.search(normalized):
                    return pattern.pattern
        return None

    def _unsafe_path(self, path: str) -> bool:
        if not path or path.startswith("/") or "\\" in path:
            return True
        parts = PurePosixPath(path).parts
        if ".." in parts:
            return True
        lowered = path.lower()
        return any(fragment in lowered for fragment in self.sensitive_fragments)
