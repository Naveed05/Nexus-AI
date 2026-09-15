from nexus.core.failure_predictor import FailurePredictor
from nexus.core.orchestrator import TaskDecomposer
from nexus.core.plan_optimizer import PlanOptimizer
from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.risk_predictor import RiskPredictor
from nexus.core.task import Task


def test_risk_prediction_is_deterministic_and_explains_signals():
    task = Task(objective="research autonomous agents and compare evidence")
    plan = TaskDecomposer().decompose(task)
    assessment = ReasoningAssessment("research", 0.9, 0.5, ("uncertainty",), ())
    optimization = PlanOptimizer().optimize(plan, assessment)

    first = RiskPredictor().predict(assessment, optimization, plan)
    second = RiskPredictor().predict(assessment, optimization, plan)

    assert first == second
    assert 0.0 <= first.score <= 1.0
    assert first.level in {"low", "medium", "high"}
    assert first.signals
    assert first.mitigations


def test_failure_predictor_surfaces_complexity_and_risk_modes():
    task = Task(objective="research autonomous agents")
    plan = TaskDecomposer().decompose(task)
    assessment = ReasoningAssessment("research", 0.9, 0.5, ("uncertainty",), ())
    optimization = PlanOptimizer().optimize(plan, assessment)
    risk = RiskPredictor().predict(assessment, optimization, plan)

    result = FailurePredictor().predict(assessment, risk, plan)

    assert 0.0 <= result.probability <= 1.0
    assert result.failure_modes
    assert result.preventive_actions
    assert "insufficient_confidence" in result.failure_modes


def test_low_risk_plan_still_keeps_verification_safeguard():
    task = Task(objective="summarize a short objective")
    plan = TaskDecomposer().decompose(task)
    assessment = ReasoningAssessment("general", 0.5, 0.95, (), ())
    optimization = PlanOptimizer().optimize(plan, assessment)
    risk = RiskPredictor().predict(assessment, optimization, plan)
    result = FailurePredictor().predict(assessment, risk, plan)

    assert risk.level == "low"
    assert "generic_execution_failure" in result.failure_modes
    assert "retain_verification_gate" in result.preventive_actions
