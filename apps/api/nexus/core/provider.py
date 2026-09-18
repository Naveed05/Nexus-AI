from dataclasses import dataclass
from typing import Any, Mapping

from nexus.core.models import ModelProvider, ModelResponse, ModelSpec


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
