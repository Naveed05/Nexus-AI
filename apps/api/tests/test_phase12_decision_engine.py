from nexus.core.decision_engine import DecisionEngine
from nexus.core.decision_guard import DecisionGuard
from nexus.core.plan_optimizer import PlanOptimization
from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.risk_predictor import RiskPrediction
from nexus.core.strategy_selector import StrategySelection


def assessment(complexity=0.3, confidence=0.9, risks=()):
    return ReasoningAssessment("general", complexity, confidence, tuple(risks), ())


def optimization(score=0.95, priority="low"):
    return PlanOptimization(score, priority, ())


def strategy(name="direct"):
    return StrategySelection(name, (), 0.8)


def test_decision_engine_is_deterministic_and_risk_aware():
    engine = DecisionEngine()
    low = RiskPrediction(0.1, "low", (), ())
    first = engine.decide(assessment(), optimization(), low, strategy())
    second = engine.decide(assessment(), optimization(), low, strategy())
    assert first == second
    assert first.action == "proceed"

    high = RiskPrediction(0.85, "high", ("known_risks",), ("apply_risk_controls",))
    guarded = engine.decide(assessment(confidence=0.7, complexity=0.8), optimization(), high, strategy("cautious"))
    assert guarded.action == "review"
    assert "require_review" in guarded.safeguards


def test_decision_guard_blocks_unsafe_autonomy():
    guard = DecisionGuard()
    low_confidence = DecisionEngine().decide(
        assessment(confidence=0.5), optimization(), RiskPrediction(0.2, "low", (), ()), strategy()
    )
    result = guard.evaluate(low_confidence)
    assert not result.allowed
    assert result.action == "review"

    staged = DecisionEngine().decide(
        assessment(complexity=0.9), optimization(), RiskPrediction(0.2, "low", (), ()), strategy("cautious")
    )
    result = guard.evaluate(staged)
    assert result.allowed
    assert result.action == "stage"
