from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    key: str
    model_id: str
    provider: str
    tier: str
    description: str
    capabilities: frozenset[str]
    reasoning_levels: frozenset[str]
    context_window: int
    supports_tools: bool
    cost_score: int
    latency_score: int


class ModelRegistry:
    """Extensible registry for NEXUS model providers and capabilities."""

    def __init__(self) -> None:
        self._models: dict[str, ModelSpec] = {}
        self.register(
            ModelSpec(
                key="astra",
                model_id="gpt-6-astra",
                provider="openai",
                tier="flagship",
                description="Hardest end-to-end reasoning, coding, research, and agentic work.",
                capabilities=frozenset({"reasoning", "coding", "research", "agentic", "multimodal", "tools"}),
                reasoning_levels=frozenset({"low", "medium", "high", "xhigh", "max"}),
                context_window=1_050_000,
                supports_tools=True,
                cost_score=5,
                latency_score=2,
            )
        )
        self.register(
            ModelSpec(
                key="sol",
                model_id="gpt-5.6-sol",
                provider="openai",
                tier="professional",
                description="Complex professional work with a lower cost profile than Astra.",
                capabilities=frozenset({"reasoning", "coding", "research", "tools"}),
                reasoning_levels=frozenset({"low", "medium", "high"}),
                context_window=400_000,
                supports_tools=True,
                cost_score=3,
                latency_score=3,
            )
        )
        self.register(
            ModelSpec(
                key="terra",
                model_id="gpt-5.6-terra",
                provider="openai",
                tier="balanced",
                description="Balanced intelligence and cost for general NEXUS workloads.",
                capabilities=frozenset({"reasoning", "coding", "tools"}),
                reasoning_levels=frozenset({"low", "medium"}),
                context_window=200_000,
                supports_tools=True,
                cost_score=2,
                latency_score=4,
            )
        )
        self.register(
            ModelSpec(
                key="luna",
                model_id="gpt-5.6-luna",
                provider="openai",
                tier="economy",
                description="Cost-sensitive, high-volume workloads.",
                capabilities=frozenset({"reasoning", "tools"}),
                reasoning_levels=frozenset({"low"}),
                context_window=128_000,
                supports_tools=True,
                cost_score=1,
                latency_score=5,
            )
        )

    def register(self, spec: ModelSpec) -> None:
        if spec.key in self._models:
            raise ValueError(f"Model key already registered: {spec.key}")
        self._models[spec.key] = spec

    def get(self, key: str) -> ModelSpec:
        try:
            return self._models[key]
        except KeyError as exc:
            raise ValueError(f"Unknown model: {key}") from exc

    def all(self) -> tuple[ModelSpec, ...]:
        return tuple(self._models.values())


model_registry = ModelRegistry()
