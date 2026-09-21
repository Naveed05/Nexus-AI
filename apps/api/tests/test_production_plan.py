from nexus.core.production_plan import ProductionPlanner
from nexus.core.state import PlanStep
from nexus.core.task import Task


def test_production_plan_is_explainable_and_capability_safe():
    task = Task(objective="calculate average revenue", capabilities=("calculation",))
    step = PlanStep(step_id="step-1", objective="calculate the average")

    plan = ProductionPlanner().build(task, (step,))

    assert plan.routing.model is not None
    assert plan.capability_safe is True
    assert plan.tools[0].tool is not None
    assert plan.reasons


def test_production_plan_handles_tool_gap_deterministically():
    task = Task(objective="perform an unsupported capability", capabilities=("quantum_simulation",))
    step = PlanStep(step_id="step-1", objective="perform quantum simulation")

    plan = ProductionPlanner().build(task, (step,))

    assert plan.capability_safe is False
    assert plan.tools[0].tool is None
