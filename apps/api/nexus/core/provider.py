from dataclasses import dataclass
from typing import Any, Mapping

from nexus.core.models import ModelProvider, ModelResponse, ModelSpec, model_registry


@dataclass(frozen=True)
class StaticModelProvider:
    """Deterministic provider adapter useful for local execution and tests."""
    name: str = "static"
    response_text: str = ""

    def generate(
        self,
        *,
        model: ModelSpec,
        input_items: list[Any],
        tools: list[Mapping[str, Any]],
        tool_choice: str,
    ) -> ModelResponse:
        return ModelResponse(
            output=self.response_text,
            response_id="static-response",
            provider=self.name,
            model_id=model.model_id,
        )


@dataclass(frozen=True)
class ProviderRoute:
    """Resolved model/provider pair used by the execution layer."""
    model: ModelSpec
    provider: ModelProvider
    fallback_index: int = 0


@dataclass(frozen=True)
class ModelFallbackPolicy:
    """Deterministic ordered fallback models for provider failures."""
    fallback_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.fallback_keys)) != len(self.fallback_keys):
            raise ValueError("fallback models must be unique")
        for key in self.fallback_keys:
            if not key.strip():
                raise ValueError("fallback model key cannot be blank")

    def candidates(self, primary: ModelSpec) -> tuple[ModelSpec, ...]:
        models = [primary]
        seen = {primary.key}
        for key in self.fallback_keys:
            model = model_registry.get(key)
            if model.key not in seen:
                models.append(model)
                seen.add(model.key)
        return tuple(models)


class ModelProviderRouter:
    """Resolves routed models to providers and deterministic fallbacks."""

    def __init__(self, registry: Any, fallback_policy: ModelFallbackPolicy | None = None) -> None:
        self.registry = registry
        self.fallback_policy = fallback_policy or ModelFallbackPolicy()

    def route(self, model: ModelSpec, *, fallback_index: int = 0) -> ProviderRoute:
        candidates = self.fallback_policy.candidates(model)
        if fallback_index < 0 or fallback_index >= len(candidates):
            raise ValueError("fallback index is out of range")
        selected = candidates[fallback_index]
        return ProviderRoute(
            model=selected,
            provider=self.registry.get(selected.provider),
            fallback_index=fallback_index,
        )

    def fallback(self, model: ModelSpec, *, failed_index: int = 0) -> ProviderRoute | None:
        candidates = self.fallback_policy.candidates(model)
        next_index = failed_index + 1
        if next_index >= len(candidates):
            return None
        return self.route(model, fallback_index=next_index)


class ModelProviderRegistry:
    """Registry that binds provider names to explicit adapters."""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        name = provider.name.strip().lower()
        if not name:
            raise ValueError("provider name cannot be blank")
        if name in self._providers:
            raise ValueError(f"Provider already registered: {name}")
        self._providers[name] = provider

    def get(self, name: str) -> ModelProvider:
        key = name.strip().lower()
        try:
            return self._providers[key]
        except KeyError as exc:
            raise ValueError(f"Unknown model provider: {name}") from exc

    def all(self) -> tuple[ModelProvider, ...]:
        return tuple(self._providers.values())


provider_registry = ModelProviderRegistry()
