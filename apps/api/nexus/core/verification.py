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
    checks: dict[str, bool]
    issues: tuple[str, ...] = ()


class OutputVerifier:
    """Deterministic first-pass verifier for observable execution properties."""

    def verify(self, task: Task, output: str, tool_calls: tuple[Any, ...] = ()) -> VerificationResult:
        objective_present = bool(task.objective.strip())
        output_present = bool(output.strip())
        tools_recorded = all(bool(getattr(call, "tool_name", "")) for call in tool_calls)
        checks = {
            "non_empty_output": output_present,
            "objective_present": objective_present,
            "tool_calls_recorded": tools_recorded,
        }
        messages = {
            "non_empty_output": "Output is non-empty." if output_present else "Model returned empty output.",
            "objective_present": "Task objective is present." if objective_present else "Task objective is empty.",
            "tool_calls_recorded": "Tool calls are recorded correctly." if tools_recorded else "A tool call is missing its name.",
        }
        return VerificationResult(
            passed=all(checks.values()),
            checks=checks,
            issues=tuple(messages[name] for name, passed in checks.items() if not passed),
        )
