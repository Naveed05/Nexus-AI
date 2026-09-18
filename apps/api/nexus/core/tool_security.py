from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ToolSecurityPolicy:
    """Deterministic input boundary for registered tool execution."""

    max_argument_bytes: int = 64 * 1024
    denied_argument_names: frozenset[str] = frozenset({"password", "secret", "private_key", "credential"})

    def __post_init__(self) -> None:
        if self.max_argument_bytes < 1:
            raise ValueError("max_argument_bytes must be greater than zero")
        normalized = frozenset(name.strip().lower() for name in self.denied_argument_names)
        if any(not name for name in normalized):
            raise ValueError("denied argument names cannot be blank")
        object.__setattr__(self, "denied_argument_names", normalized)

    def validate(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise ValueError("tool arguments must be an object")
        names = {str(name).strip().lower() for name in arguments}
        denied = sorted(names & self.denied_argument_names)
        if denied:
            raise ValueError(f"tool arguments contain restricted fields: {', '.join(denied)}")
        normalized = dict(arguments)
        import json
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        if len(encoded) > self.max_argument_bytes:
            raise ValueError("tool argument payload exceeds security limit")
        return normalized
