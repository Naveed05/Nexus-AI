from dataclasses import dataclass

from nexus.core.orchestrator import TaskPlan
from nexus.core.reasoning_engine import ReasoningAssessment


@dataclass(frozen=True)
class PlanOptimization:
    """Reviewable optimization guidance for an existing task plan."""

    score: float
    priority: str
    recommendations: tuple[str, ...]


class PlanOptimizer:
    """Score a plan against reasoning signals without mutating or executing it."""

    def optimize(self, plan: TaskPlan, assessment: ReasoningAssessment) -> PlanOptimization:
        steps = plan.steps
        score = 0.55
        recommendations: list[str] = []

        if steps and steps[-1].step_id == "deliver":
            score += 0.12
        else:
            recommendations.append("add an explicit delivery step")

        if any(step.step_id == "verify" for step in steps):
            score += 0.18
        else:
            recommendations.append("add an explicit verification gate")

        if any(step.depends_on for step in steps):
            score += 0.08
        else:
            recommendations.append("introduce dependencies between related steps")

        if assessment.confidence < 0.6:
            recommendations.append("request or gather additional context before execution")
        if assessment.complexity > 0.75 and len(steps) < 4:
            recommendations.append("decompose the objective into smaller verifiable steps")

        score = round(min(1.0, score), 3)
        if score < 0.6:
            priority = "high"
        elif score < 0.8:
            priority = "medium"
        else:
            priority = "low"
        return PlanOptimization(score=score, priority=priority, recommendations=tuple(recommendations))
