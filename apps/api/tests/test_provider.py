import pytest

from nexus.core.models import ModelResponse, ModelSpec
from nexus.core.provider import (
    ModelFallbackPolicy,
    ModelProviderRouter,
    ModelProviderRegistry,
    StaticModelProvider,
)


def _model(provider: str = "static") -> ModelSpec:
    return ModelSpec(
        key="test-model",
        model_id="test-model-id",
        provider=provider,
        tier="test",
        description="test",
        capabilities=frozenset({"reasoning"}),
        reasoning_levels=frozenset({"low"}),
        context_window=1000,
        supports_tools=False,
        cost_score=1,
        latency_score=1,
    )


def test_static_provider_returns_structured_response() -> None:
    provider = StaticModelProvider(response_text="hello")
    response = provider.generate(model=_model(), input_items=[], tools=[], tool_choice="auto")
    assert isinstance(response, ModelResponse)
    assert response.output == "hello"
    assert response.provider == "static"
    assert response.model_id == "test-model-id"


def test_provider_router_resolves_model_provider() -> None:
    registry = ModelProviderRegistry()
    provider = StaticModelProvider()
    registry.register(provider)
    route = ModelProviderRouter(registry).route(_model())
    assert route.model.key == "test-model"
    assert route.provider is provider
    assert route.fallback_index == 0


def test_fallback_policy_is_ordered_and_skips_primary() -> None:
    policy = ModelFallbackPolicy(("terra", "luna"))
    candidates = policy.candidates(__import__("nexus.core.models", fromlist=["model_registry"]).model_registry.get("terra"))
    assert [model.key for model in candidates] == ["terra", "luna"]


def test_provider_router_moves_to_next_fallback() -> None:
    registry = ModelProviderRegistry()
    registry.register(StaticModelProvider(name="openai"))
    policy = ModelFallbackPolicy(("terra", "luna"))
    router = ModelProviderRouter(registry, policy)
    first = router.route(__import__("nexus.core.models", fromlist=["model_registry"]).model_registry.get("terra"))
    assert first.fallback_index == 0
    second = router.fallback(first.model, failed_index=first.fallback_index)
    assert second is not None
    assert second.model.key == "luna"
    assert second.fallback_index == 1


def test_fallback_returns_none_after_last_candidate() -> None:
    registry = ModelProviderRegistry()
    registry.register(StaticModelProvider(name="openai"))
    router = ModelProviderRouter(registry, ModelFallbackPolicy(("luna",)))
    primary = __import__("nexus.core.models", fromlist=["model_registry"]).model_registry.get("terra")
    assert router.fallback(primary, failed_index=1) is None


def test_fallback_policy_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="unique"):
        ModelFallbackPolicy(("luna", "luna"))
