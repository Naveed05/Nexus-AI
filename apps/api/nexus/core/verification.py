import re
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
    """Deterministic verifier for observable execution and research-grounding properties."""

    _citation_pattern = re.compile(r"\[Source:\s*([^\]]+)\]")

    @staticmethod
    def _is_research_task(task: Task, tool_calls: tuple[Any, ...]) -> bool:
        capabilities = {capability.lower() for capability in task.capabilities}
        return bool(capabilities.intersection({"research", "synthesize"})) or any(
            getattr(call, "tool_name", "") == "search_knowledge" for call in tool_calls
        )

    def _verify_grounding(
        self,
        task: Task,
        output: str,
        tool_calls: tuple[Any, ...],
        grounded_evidence: tuple[dict[str, Any], ...],
    ) -> tuple[bool, str]:
        if not self._is_research_task(task, tool_calls):
            return True, "Grounding check not required for this task."

        if not grounded_evidence:
            return False, "Research task produced no retrieved evidence."

        citations = self._citation_pattern.findall(output)
        if not citations:
            return False, "Research output does not contain a citation to retrieved evidence."

        available = {
            str(item.get("citation")).strip()
            for item in grounded_evidence
            if item.get("citation")
        }
        unsupported = [citation.strip() for citation in citations if citation.strip() not in available]
        if unsupported:
            return False, f"Research output contains unsupported citations: {', '.join(unsupported)}"

        return True, "Research output cites retrieved evidence."

    def verify(
        self,
        task: Task,
        output: str,
        tool_calls: tuple[Any, ...] = (),
        grounded_evidence: tuple[dict[str, Any], ...] = (),
    ) -> VerificationResult:
        objective_present = bool(task.objective.strip())
        output_present = bool(output.strip())
        tools_recorded = all(bool(getattr(call, "tool_name", "")) for call in tool_calls)
        grounding_passed, grounding_message = self._verify_grounding(
            task,
            output,
            tool_calls,
            grounded_evidence,
        )
        checks = {
            "non_empty_output": output_present,
            "objective_present": objective_present,
            "tool_calls_recorded": tools_recorded,
            "grounded_research": grounding_passed,
        }
        messages = {
            "non_empty_output": "Output is non-empty." if output_present else "Model returned empty output.",
            "objective_present": "Task objective is present." if objective_present else "Task objective is empty.",
            "tool_calls_recorded": "Tool calls are recorded correctly." if tools_recorded else "A tool call is missing its name.",
            "grounded_research": grounding_message,
        }
        return VerificationResult(
            passed=all(checks.values()),
            checks=checks,
            issues=tuple(messages[name] for name, passed in checks.items() if not passed),
        )
