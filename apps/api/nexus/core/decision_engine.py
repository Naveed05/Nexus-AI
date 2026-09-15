from dataclasses import dataclass
from typing import Tuple

from nexus.core.plan_optimizer import PlanOptimization
from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.risk_predictor import RiskPrediction
from nexus.core.strategy_selector import StrategySelection


@dataclass(frozen=True)
class Decision:
    action: str
    rationale: str
    confidence: float
    safeguards: Tuple[str, ...]


class DecisionEngine:
    """Combines bounded intelligence signals into an execution-safe decision."""

    def decide(
        self,
        assessment: ReasoningAssessment,
        optimization: PlanOptimization,
        risk: RiskPrediction,
        strategy: StrategySelection,
    ) -> Decision:
        safeguards = list(risk.mitigations)
        confidence = min(assessment.confidence, optimization.score, 1.0 - (risk.score * 0.5))

        if risk.level == "high":
            action = "review"
            rationale = "High predicted execution risk requires review before execution."
            safeguards.extend(("require_review", "preserve_checkpoint"))
        elif strategy.strategy == "cautious":
            action = "stage"
            rationale = "Complexity or risk signals favor staged execution."
            safeguards.append("verify_each_stage")
        elif strategy.strategy == "review":
            action = "review"
            rationale = "Plan quality signals favor revalidation before execution."
            safeguards.append("revalidate_plan")
        else:
            action = "proceed"
            rationale = f"Selected {strategy.strategy} strategy within bounded risk limits."

        return Decision(
            action=action,
            rationale=rationale,
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            safeguards=tuple(dict.fromkeys(safeguards)),
        )
