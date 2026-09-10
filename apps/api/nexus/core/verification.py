from dataclasses import dataclass
from typing import Any

from nexus.core.task import Task


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: dict[str, bool]
    issues: tuple[str, ...] = ()


class OutputVerifier:
    """Deterministic first-pass verifier for agent outputs.

    This intentionally checks observable properties only. Model-based critique,
    grounding checks, and domain-specific validation will be layered on later.
    """

    def verify(self, task: Task, output: str, tool_calls: tuple[Any, ...] = ()) -> VerificationResult:
        checks = {
            "non_empty_output": bool(output.strip()),
            "objective_present": bool(task.objective.strip()),
            "tool_calls_recorded": all(
                bool(getattr(call, "tool_name", "")) for call in tool_calls
            ),
        }
        issues: list[str] = []
        if not checks["non_empty_output"]:
            issues.append("Model returned empty output.")
        if not checks["objective_present"]:
            issues.append("Task objective is empty.")
        if not checks["tool_calls_recorded"]:
            issues.append("One or more tool calls are missing a tool name.")

        return VerificationResult(
            passed=all(checks.values()),
            checks=checks,
            issues=tuple(issues),
        )
