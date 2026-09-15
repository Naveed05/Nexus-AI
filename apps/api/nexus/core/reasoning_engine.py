from dataclasses import dataclass

from nexus.core.task import RiskLevel, Task


@dataclass(frozen=True)
class ReasoningAssessment:
    """Deterministic reasoning assessment for a task before orchestration."""

    intent: str
    complexity: float
    confidence: float
    risks: tuple[str, ...]
    assumptions: tuple[str, ...]


class ReasoningEngine:
    """Estimate task intent, complexity, confidence, and explicit uncertainty."""

    _intent_signals = {
        "coding": ("code", "debug", "repository", "implement", "fix bug"),
        "research": ("research", "literature", "compare studies", "investigate", "sources"),
        "data": ("dataset", "data", "dataframe", "csv", "xlsx", "analysis"),
    }

    def assess(self, task: Task) -> ReasoningAssessment:
        text = task.objective.strip().lower()
        matches = sorted(
            intent
            for intent, signals in self._intent_signals.items()
            if any(signal in text for signal in signals)
        )
        intent = matches[0] if matches else "general"

        signal_count = sum(text.count(signal) for signals in self._intent_signals.values() for signal in signals)
        constraint_factor = min(len(task.constraints) * 0.08, 0.32)
        context_factor = 0.08 if task.context and task.context.strip() else 0.0
        complexity = min(1.0, 0.2 + min(len(text) / 500, 0.35) + constraint_factor + (0.15 if len(matches) > 1 else 0.0))

        risks: list[str] = []
        if task.risk_level == RiskLevel.HIGH:
            risks.append("high-risk task requires explicit verification")
        elif task.risk_level == RiskLevel.MEDIUM:
            risks.append("medium-risk task requires careful verification")
        if task.budget is not None and task.budget == 0:
            risks.append("zero execution budget may prevent tool-backed work")
        if len(task.constraints) > 3:
            risks.append("multiple constraints increase failure surface")
        if signal_count == 0:
            risks.append("intent is inferred from general task structure")

        confidence = max(0.35, min(0.98, 0.72 + context_factor + (0.08 if matches else 0.0) - constraint_factor))
        assumptions: list[str] = []
        if not task.context:
            assumptions.append("no additional task context was supplied")
        if not task.capabilities:
            assumptions.append("no explicit capability preference was supplied")
        return ReasoningAssessment(
            intent=intent,
            complexity=round(complexity, 3),
            confidence=round(confidence, 3),
            risks=tuple(risks),
            assumptions=tuple(assumptions),
        )
