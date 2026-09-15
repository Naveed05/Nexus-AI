from dataclasses import dataclass
from typing import Tuple

from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.plan_optimizer import PlanOptimization
from nexus.core.orchestrator import TaskPlan


@dataclass(frozen=True)
class RiskPrediction:
    score: float
    level: str
    signals: Tuple[str, ...]
    mitigations: Tuple[str, ...]


class RiskPredictor:
    """Deterministically predicts execution risk without executing a plan."""

    def predict(
        self,
        assessment: ReasoningAssessment,
        optimization: PlanOptimization,
        plan: TaskPlan,
    ) -> RiskPrediction:
        score = 0.0
        signals = []
        mitigations = []

        score += max(0.0, min(1.0, 1.0 - assessment.confidence)) * 0.35
        score += max(0.0, min(1.0, assessment.complexity)) * 0.25
        score += max(0.0, min(1.0, 1.0 - optimization.score)) * 0.20
        score += min(0.20, len(assessment.risks) * 0.05)

        if assessment.confidence < 0.6:
            signals.append("low_confidence")
            mitigations.append("increase_verification")
        if assessment.complexity >= 0.75:
            signals.append("high_complexity")
            mitigations.append("decompose_or_stage")
        if assessment.risks:
            signals.append("known_risks")
            mitigations.append("apply_risk_controls")
        if len(plan.steps) >= 5:
            signals.append("long_execution_path")
            mitigations.append("checkpoint_progress")
        if optimization.score < 0.6:
            signals.append("weak_plan_quality")
            mitigations.append("review_plan_before_execution")

        score = round(min(1.0, score), 4)
        level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
        return RiskPrediction(score, level, tuple(signals), tuple(mitigations))
