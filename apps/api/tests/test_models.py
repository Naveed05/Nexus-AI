import pytest

from nexus.core.models import ModelSpec, model_registry


def test_model_spec_contract_and_reasoning_metadata() -> None:
    model = model_registry.get("astra")
    contract = model.contract()
    assert contract["key"] == "astra"
    assert contract["maximum_reasoning"] == "max"
    assert contract["supports_tools"] is True
    assert contract["context_window"] == 1_050_000
    assert "reasoning" in contract["capabilities"]


def test_model_fit_rejects_missing_capability_and_excess_context() -> None:
    model = model_registry.get("luna")
    fits, score, reasons = model.fit_score(required_capabilities={"coding"})
    assert fits is False
    assert score == 0
    assert "missing capabilities" in reasons[0]

    fits, _, reasons = model.fit_score(estimated_input_tokens=model.context_window + 1)
    assert fits is False
    assert "context window" in reasons[0]


def test_model_fit_enforces_reasoning_and_tools() -> None:
    model = model_registry.get("terra")
    fits, _, reasons = model.fit_score(reasoning_level="medium", needs_tools=True)
    assert fits is True
    assert any("reasoning" in reason for reason in reasons)

    fits, _, _ = model.fit_score(reasoning_level="high")
    assert fits is False


def test_model_registry_find_is_deterministic() -> None:
    matches = model_registry.find(required_capabilities={"coding"}, reasoning_level="medium", needs_tools=True)
    assert [model.key for model in matches] == sorted(model.key for model in matches)
    assert {model.key for model in matches} == {"astra", "sol", "terra"}


def test_model_spec_rejects_invalid_reasoning_level() -> None:
    with pytest.raises(ValueError, match="unsupported reasoning levels"):
        ModelSpec(
            key="invalid",
            model_id="invalid",
            provider="test",
            tier="test",
            description="test",
            capabilities=frozenset({"reasoning"}),
            reasoning_levels=frozenset({"quantum"}),
            context_window=100,
            supports_tools=False,
            cost_score=1,
            latency_score=1,
        )
