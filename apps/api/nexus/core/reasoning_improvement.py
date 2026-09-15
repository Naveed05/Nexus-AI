from dataclasses import dataclass

from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.self_critique import ReasoningCritique


@dataclass(frozen=True)
class ReasoningImprovement:
    """An improved assessment plus an auditable description of what changed."""

    original: ReasoningAssessment
    improved: ReasoningAssessment
    changes: tuple[str, ...]


class ReasoningImprovementLoop:
    """Apply bounded, deterministic corrections identified by self-critique."""

    def improve(
        self, assessment: ReasoningAssessment, critique: ReasoningCritique
    ) -> ReasoningImprovement:
        confidence = assessment.confidence
        complexity = assessment.complexity
        risks = list(assessment.risks)
        assumptions = list(assessment.assumptions)
        changes: list[str] = []

        if critique.weaknesses and "reasoning confidence is low" not in critique.weaknesses:
            confidence = max(0.35, confidence - 0.05)
            changes.append("reduced confidence to account for identified weaknesses")
        elif critique.missing_evidence:
            confidence = max(0.35, confidence - 0.05)
            changes.append("reduced confidence because supporting context is incomplete")

        if critique.contradictions:
            confidence = max(0.35, confidence - 0.1)
            changes.append("reduced confidence because a reasoning contradiction was detected")

        if critique.weaknesses or critique.missing_evidence:
            complexity = min(1.0, complexity + 0.05)
            changes.append("increased complexity to reflect reasoning uncertainty")

        if critique.missing_evidence and "additional evidence should be gathered before execution" not in risks:
            risks.append("additional evidence should be gathered before execution")
            changes.append("added an evidence-gathering risk")

        if critique.contradictions and "intent requires re-validation before execution" not in assumptions:
            assumptions.append("intent requires re-validation before execution")
            changes.append("added an intent re-validation assumption")

        improved = ReasoningAssessment(
            intent=assessment.intent,
            complexity=round(complexity, 3),
            confidence=round(confidence, 3),
            risks=tuple(risks),
            assumptions=tuple(assumptions),
        )
        return ReasoningImprovement(
            original=assessment,
            improved=improved,
            changes=tuple(changes),
        )
