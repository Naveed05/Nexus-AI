from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    key: str
    model_id: str
    provider: str
    tier: str
    description: str


class ModelRegistry:
    def __init__(self) -> None:
        self._models = {
            "astra": ModelSpec(
                key="astra",
                model_id="gpt-6-astra",
                provider="openai",
                tier="flagship",
                description="Hardest end-to-end reasoning, coding, research, and agentic work.",
            ),
            "sol": ModelSpec(
                key="sol",
                model_id="gpt-5.6-sol",
                provider="openai",
                tier="professional",
                description="Complex professional work with a lower cost profile than Astra.",
            ),
            "terra": ModelSpec(
                key="terra",
                model_id="gpt-5.6-terra",
                provider="openai",
                tier="balanced",
                description="Balanced intelligence and cost for general NEXUS workloads.",
            ),
            "luna": ModelSpec(
                key="luna",
                model_id="gpt-5.6-luna",
                provider="openai",
                tier="economy",
                description="Cost-sensitive, high-volume workloads.",
            ),
        }

    def get(self, key: str) -> ModelSpec:
        try:
            return self._models[key]
        except KeyError as exc:
            raise ValueError(f"Unknown model: {key}") from exc

    def all(self) -> tuple[ModelSpec, ...]:
        return tuple(self._models.values())


model_registry = ModelRegistry()
