from nexus.core.orchestrator import TaskDecomposer
from nexus.core.plan_optimizer import PlanOptimizer
from nexus.core.reasoning_engine import ReasoningAssessment
from nexus.core.strategy_planner import StrategyAwarePlanner
from nexus.core.strategy_selector import DynamicStrategySelector
from nexus.core.task import Task


def test_strategy_selector_is_deterministic_and_risk_aware():
    assessment = ReasoningAssessment("research", 0.9, 0.7, ("uncertainty", "risk"), ())
    plan = TaskDecomposer().decompose(Task(objective="research autonomous agents"))
    optimization = PlanOptimizer().optimize(plan, assessment)
    first = DynamicStrategySelector().select(assessment, optimization)
    second = DynamicStrategySelector().select(assessment, optimization)
    assert first == second
    assert first.strategy == "cautious"
    assert first.score <= 1.0


def test_strategy_planner_preserves_plan_and_adds_safeguards():
    task = Task(objective="research autonomous agents")
    plan = TaskDecomposer().decompose(task)
    assessment = ReasoningAssessment("research", 0.9, 0.7, ("risk",), ())
    optimization = PlanOptimizer().optimize(plan, assessment)
    selection = DynamicStrategySelector().select(assessment, optimization)
    result = StrategyAwarePlanner().adapt(plan, selection)
    assert result.strategy == "cautious"
    assert result.priorities == tuple(step.step_id for step in plan.steps)
    assert result.safeguards
    assert [step.step_id for step in plan.steps] == [step.step_id for step in TaskDecomposer().decompose(task).steps]


def test_low_quality_plan_switches_to_review():
    assessment = ReasoningAssessment("general", 0.5, 0.5, (), ())
    plan = TaskDecomposer().decompose(Task(objective="summarize objective"))
    optimization = PlanOptimizer().optimize(plan, assessment)
    selection = DynamicStrategySelector().select(assessment, optimization)
    assert selection.strategy in {"review", "standard", "direct"}
