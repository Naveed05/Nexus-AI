import pytest
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


def test_model_registry_filters_explicit_requirements() -> None:
    from nexus.core.models import ModelRequirements

    matches = model_registry.find(ModelRequirements(
        required_capabilities=frozenset({"coding"}),
        reasoning_level="high",
        require_tools=True,
    ))
    assert {model.key for model in matches} == {"astra", "sol"}
    assert matches[0].cost_score <= matches[1].cost_score


def test_model_registry_rejects_incompatible_model() -> None:
    from nexus.core.models import ModelCapabilityError, ModelRequirements

    requirements = ModelRequirements(
        required_capabilities=frozenset({"research"}),
        reasoning_level="high",
    )
    with pytest.raises(ModelCapabilityError):
        model_registry.validate(model_registry.get("terra"), requirements)


def test_router_exposes_explainable_multi_factor_candidates() -> None:
    task = Task(objective="Write production Python code", capabilities=["coding"])
    decision = router.decide(task)

    assert decision.model.key == "sol"
    assert decision.candidates
    assert {candidate.model.key for candidate in decision.candidates} == {"astra", "sol"}
    assert all(candidate.total >= 0 for candidate in decision.candidates)
    assert all(candidate.capability_fit == 1.0 for candidate in decision.candidates)


def test_router_hard_signal_requires_high_reasoning_candidates() -> None:
    task = Task(objective="Research and reason about a complex architecture")
    decision = router.decide(task)

    assert decision.model.key == "astra"
    assert {candidate.model.key for candidate in decision.candidates} == {"astra", "sol"}
    assert all(candidate.reasoning_fit == 1.0 for candidate in decision.candidates)


def test_router_budget_gate_limits_candidates_to_luna() -> None:
    task = Task(objective="Summarize this", budget=1)
    decision = router.decide(task)

    assert decision.model.key == "luna"
    assert [candidate.model.key for candidate in decision.candidates] == ["luna"]
