from dataclasses import dataclass
from typing import Any

from nexus.core.task import Task


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: tuple[VerificationCheck, ...]
    issues: tuple[str, ...] = ()


class OutputVerifier:
    """Deterministic first-pass verifier for observable execution properties."""

    def verify(self, task: Task, output: str, tool_calls: tuple[Any, ...] = ()) -> VerificationResult:
        objective_present = bool(task.objective.strip())
        output_present = bool(output.strip())
        tools_recorded = all(bool(getattr(call, "tool_name", "")) for call in tool_calls)
        checks = (
            VerificationCheck("non_empty_output", output_present, "Output is non-empty." if output_present else "Output is empty."),
            VerificationCheck("objective_present", objective_present, "Task objective is present." if objective_present else "Task objective is empty."),
            VerificationCheck("tool_calls_recorded", tools_recorded, "Tool calls are recorded correctly." if tools_recorded else "A tool call is missing its name."),
        )
        return VerificationResult(
            passed=all(check.passed for check in checks),
            checks=checks,
            issues=tuple(check.message for check in checks if not check.passed),
        )
