from dataclasses import dataclass
from typing import Tuple

from nexus.core.orchestrator import TaskPlan
from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.risk_predictor import RiskPrediction


@dataclass(frozen=True)
class FailurePrediction:
    probability: float
    failure_modes: Tuple[str, ...]
    preventive_actions: Tuple[str, ...]


class FailurePredictor:
    """Identifies likely failure modes before execution begins."""

    def predict(
        self,
        assessment: ReasoningAssessment,
        risk: RiskPrediction,
        plan: TaskPlan,
    ) -> FailurePrediction:
        probability = risk.score * 0.7
        modes = []
        actions = []

        if assessment.confidence < 0.6:
            modes.append("insufficient_confidence")
            actions.append("require_stronger_verification")
        if assessment.complexity >= 0.75:
            modes.append("complexity_overrun")
            actions.append("stage_execution")
        if assessment.risks:
            modes.append("unmitigated_risk")
            actions.append("apply_predicted_mitigations")
        if len(plan.steps) >= 5:
            modes.append("dependency_or_progress_failure")
            actions.append("checkpoint_between_stages")
        if not modes:
            modes.append("generic_execution_failure")
            actions.append("retain_verification_gate")

        probability = round(min(1.0, probability), 4)
        return FailurePrediction(probability, tuple(modes), tuple(actions))
