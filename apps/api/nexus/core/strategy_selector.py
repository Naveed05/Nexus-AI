from dataclasses import dataclass

from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.plan_optimizer import PlanOptimization


@dataclass(frozen=True)
class StrategySelection:
    """Deterministic strategy choice with an auditable rationale."""

    strategy: str
    rationale: tuple[str, ...]
    score: float


class DynamicStrategySelector:
    """Select an execution strategy from reasoning and plan signals without executing work."""

    def select(
        self, assessment: ReasoningAssessment, optimization: PlanOptimization
    ) -> StrategySelection:
        rationale: list[str] = []
        strategy = "standard"
        score = 0.5

        if assessment.complexity >= 0.75 or len(assessment.risks) >= 2:
            strategy = "cautious"
            score = 0.8
            rationale.append("high complexity or risk favors cautious planning")
        elif assessment.complexity <= 0.35 and assessment.confidence >= 0.8:
            strategy = "direct"
            score = 0.8
            rationale.append("low complexity and high confidence favor direct execution")

        if optimization.priority == "high":
            score += 0.05
            rationale.append("high plan priority increases strategy urgency")
        if optimization.score < 0.5:
            strategy = "review"
            score = min(score, 0.9)
            rationale.append("low plan quality requires review before execution")

        return StrategySelection(
            strategy=strategy,
            rationale=tuple(rationale),
            score=round(min(score, 1.0), 3),
        )
