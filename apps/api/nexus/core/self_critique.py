from dataclasses import dataclass

from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.task import Task


@dataclass(frozen=True)
class ReasoningCritique:
    """Structured critique of a reasoning assessment before it is trusted."""

    weaknesses: tuple[str, ...]
    contradictions: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    severity: str


class SelfCritiqueEngine:
    """Identify uncertainty, unsupported assumptions, and reasoning inconsistencies."""

    def critique(self, task: Task, assessment: ReasoningAssessment) -> ReasoningCritique:
        weaknesses: list[str] = []
        contradictions: list[str] = []
        missing_evidence: list[str] = []

        if assessment.confidence < 0.6:
            weaknesses.append("reasoning confidence is low")
        if assessment.complexity > 0.75 and not task.constraints:
            weaknesses.append("high complexity has limited constraint context")
        if assessment.assumptions:
            missing_evidence.append("some reasoning inputs depend on unstated context")
        if assessment.intent == "general" and any(
            signal in task.objective.lower()
            for signal in ("code", "research", "data", "dataset", "csv")
        ):
            contradictions.append("general intent conflicts with a domain-specific task signal")
        if assessment.risks and assessment.confidence > 0.9:
            weaknesses.append("high confidence may understate identified risks")

        total = len(weaknesses) + len(contradictions) + len(missing_evidence)
        severity = "high" if total >= 3 else "medium" if total >= 1 else "low"
        return ReasoningCritique(
            weaknesses=tuple(weaknesses),
            contradictions=tuple(contradictions),
            missing_evidence=tuple(missing_evidence),
            severity=severity,
        )
