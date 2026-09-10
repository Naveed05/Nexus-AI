from nexus.core.models import model_registry
from nexus.core.router import router
from nexus.core.task import RiskLevel, Task


def test_registry_contains_capability_aware_models() -> None:
    models = model_registry.all()
    assert len(models) == 4
    assert model_registry.get("astra").supports_tools is True
    assert "agentic" in model_registry.get("astra").capabilities
    assert model_registry.get("astra").context_window == 1_050_000


def test_high_risk_routes_to_astra_with_reason() -> None:
    task = Task(objective="delete production data", risk_level=RiskLevel.HIGH)
    decision = router.decide(task)

    assert decision.model.key == "astra"
    assert decision.score == 100.0
    assert "high-risk" in decision.reasons[0]


def test_complex_objective_routes_to_astra() -> None:
    task = Task(objective="Design the architecture for a multi-agent research system")
    decision = router.decide(task)

    assert decision.model.key == "astra"
    assert decision.score == 95.0


def test_professional_capability_routes_to_sol() -> None:
    task = Task(objective="Analyze this dataset", capabilities=["data_analysis"])
    decision = router.decide(task)

    assert decision.model.key == "sol"
    assert "professional-domain" in decision.reasons[0]


def test_budget_constraint_routes_to_luna() -> None:
    task = Task(objective="Summarize these notes", budget=1)
    decision = router.decide(task)

    assert decision.model.key == "luna"
    assert decision.score == 60.0


def test_general_task_routes_to_terra() -> None:
    task = Task(objective="Rewrite this paragraph")
    decision = router.decide(task)

    assert decision.model.key == "terra"
    assert decision.score == 50.0


def test_route_remains_backward_compatible() -> None:
    task = Task(objective="Explain this result")
    assert router.route(task).key == "terra"
