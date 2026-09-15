from nexus.core.orchestrator import TaskDecomposer
from nexus.core.plan_optimizer import PlanOptimizer
from nexus.core.reasoning_engine import ReasoningEngine
from nexus.core.task import Task


def test_reasoning_assessment_is_deterministic_and_explicit_about_uncertainty():
    task = Task(objective="research and compare studies about autonomous agents", constraints=["cite sources"])
    first = ReasoningEngine().assess(task)
    second = ReasoningEngine().assess(task)

    assert first == second
    assert first.intent == "research"
    assert 0.0 <= first.complexity <= 1.0
    assert 0.0 <= first.confidence <= 1.0
    assert first.assumptions


def test_plan_optimizer_reviews_existing_plan_without_mutation():
    task = Task(objective="implement a repository bug fix and test it")
    plan = TaskDecomposer().decompose(task)
    before = tuple((step.step_id, step.depends_on) for step in plan.steps)

    assessment = ReasoningEngine().assess(task)
    optimization = PlanOptimizer().optimize(plan, assessment)

    after = tuple((step.step_id, step.depends_on) for step in plan.steps)
    assert before == after
    assert 0.0 <= optimization.score <= 1.0
    assert optimization.priority in {"low", "medium", "high"}
    assert "add an explicit verification gate" not in optimization.recommendations
