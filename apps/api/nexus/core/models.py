from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen



@dataclass(frozen=True)
class ModelResponse:
    output: str
    response_id: str
    provider: str
    model_id: str
    tool_calls: tuple[Mapping[str, Any], ...] = ()



class ModelProvider(Protocol):
    name: str

    def generate(
        self,
        *,
        model: "ModelSpec",
        input_items: list[Any],
        tools: list[Mapping[str, Any]],
        tool_choice: str,
    ) -> ModelResponse:
        ...


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


class ModelCapabilityError(ValueError):
    """Raised when a model cannot satisfy an explicit capability contract."""


@dataclass(frozen=True)
class ModelRequirements:
    """Provider-neutral requirements used by routing and fallback planning."""

    required_capabilities: frozenset[str] = frozenset()
    reasoning_level: str | None = None
    minimum_context_window: int = 0
    require_tools: bool = False
    maximum_cost_score: int | None = None
    maximum_latency_score: int | None = None

    def __post_init__(self) -> None:
        if self.minimum_context_window < 0:
            raise ValueError("minimum_context_window cannot be negative")
        if self.maximum_cost_score is not None and self.maximum_cost_score < 0:
            raise ValueError("maximum_cost_score cannot be negative")
        if self.maximum_latency_score is not None and self.maximum_latency_score < 0:
            raise ValueError("maximum_latency_score cannot be negative")
        if self.reasoning_level is not None and self.reasoning_level not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported reasoning level")


@dataclass(frozen=True)
class ModelHealth:
    """Runtime health snapshot for a model/provider pair."""

    key: str
    provider: str
    available: bool = True
    consecutive_failures: int = 0
    last_error: str | None = None
    latency_ms: float | None = None


class ModelHealthRegistry:
    """Process-local health telemetry for provider/model pairs."""

    def __init__(self) -> None:
        self._health: dict[str, ModelHealth] = {}

    def _get(self, model: ModelSpec) -> ModelHealth:
        return self._health.get(
            model.key,
            ModelHealth(key=model.key, provider=model.provider),
        )

    def record_success(self, model: ModelSpec, latency_ms: float | None = None) -> ModelHealth:
        current = self._get(model)
        updated = ModelHealth(
            key=model.key,
            provider=model.provider,
            available=True,
            consecutive_failures=0,
            last_error=None,
            latency_ms=latency_ms,
        )
        self._health[model.key] = updated
        return updated

    def record_failure(self, model: ModelSpec, error: str) -> ModelHealth:
        current = self._get(model)
        updated = ModelHealth(
            key=model.key,
            provider=model.provider,
            available=False if current.consecutive_failures >= 2 else True,
            consecutive_failures=current.consecutive_failures + 1,
            last_error=error[:500],
            latency_ms=current.latency_ms,
        )
        self._health[model.key] = updated
        return updated

    def get(self, model_key: str) -> ModelHealth:
        return self._health.get(model_key, ModelHealth(key=model_key, provider="unknown"))

    def all(self) -> tuple[ModelHealth, ...]:
        return tuple(self._health[key] for key in sorted(self._health))

    def reset(self) -> None:
        self._health.clear()


model_health_registry = ModelHealthRegistry()


class ModelRegistry:
    """Extensible registry for NEXUS model providers and capabilities."""

    def __init__(self) -> None:
        self._models: dict[str, ModelSpec] = {}
        self.register(
            ModelSpec(
                key="astra",
                model_id="gpt-5.6-sol",
                provider="openai",
                tier="flagship",
                description="Flagship reasoning, coding, research, and agentic work.",
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

    def find(self, requirements: ModelRequirements) -> tuple[ModelSpec, ...]:
        matches = [
            spec for spec in self._models.values()
            if requirements.required_capabilities.issubset(spec.capabilities)
            and (requirements.reasoning_level is None or requirements.reasoning_level in spec.reasoning_levels)
            and spec.context_window >= requirements.minimum_context_window
            and (not requirements.require_tools or spec.supports_tools)
            and (requirements.maximum_cost_score is None or spec.cost_score <= requirements.maximum_cost_score)
            and (requirements.maximum_latency_score is None or spec.latency_score <= requirements.maximum_latency_score)
        ]
        return tuple(sorted(matches, key=lambda spec: (spec.cost_score, spec.latency_score, spec.key)))

    def validate(self, model: ModelSpec, requirements: ModelRequirements) -> None:
        if model not in self.find(requirements):
            raise ModelCapabilityError(
                f"model '{model.key}' does not satisfy the requested model requirements"
            )


model_registry = ModelRegistry()


class ProviderCredentialError(ValueError):
    """Raised when a BYOK credential is missing or invalid."""


class ProviderNotConfiguredError(RuntimeError):
    """Raised when a requested provider has no user credential."""


@dataclass(frozen=True)
class ProviderCredential:
    """A user-owned provider credential.

    The raw API key is intentionally never exposed by repr/serialization helpers.
    Production persistence should encrypt this value at rest.
    """

    provider: str
    key: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ProviderCredentialError("provider cannot be empty")
        if not self.key.strip():
            raise ProviderCredentialError("API key cannot be empty")

    def masked(self) -> str:
        value = self.key.strip()
        if len(value) <= 8:
            return "••••••••"
        return f"{value[:4]}••••••••{value[-4:]}"


class InMemoryCredentialStore:
    """Process-local BYOK store for development and tests.

    This deliberately avoids pretending that plaintext persistence is production
    safe. A production deployment should provide an encrypted credential store.
    """

    def __init__(self) -> None:
        self._credentials: dict[str, ProviderCredential] = {}

    def set(self, user_id: str, provider: str, api_key: str) -> None:
        if not user_id.strip():
            raise ProviderCredentialError("user_id cannot be empty")
        credential = ProviderCredential(provider=provider.strip().lower(), key=api_key.strip())
        self._credentials[f"{user_id.strip()}:{credential.provider}"] = credential

    def get(self, user_id: str, provider: str) -> ProviderCredential:
        key = f"{user_id.strip()}:{provider.strip().lower()}"
        try:
            return self._credentials[key]
        except KeyError as exc:
            raise ProviderNotConfiguredError(
                f"No API key configured for provider: {provider.strip().lower()}"
            ) from exc

    def delete(self, user_id: str, provider: str) -> None:
        self._credentials.pop(f"{user_id.strip()}:{provider.strip().lower()}", None)

    def configured_providers(self, user_id: str) -> tuple[str, ...]:
        prefix = f"{user_id.strip()}:"
        return tuple(sorted(key.removeprefix(prefix) for key in self._credentials if key.startswith(prefix)))


SUPPORTED_PROVIDERS = frozenset({"openai", "anthropic", "groq"})


class BYOKProviderManager:
    """Resolve user-owned API credentials without coupling agents to a vendor."""

    def __init__(self, credential_store: InMemoryCredentialStore | None = None) -> None:
        self._store = credential_store or InMemoryCredentialStore()

    @property
    def credential_store(self) -> InMemoryCredentialStore:
        return self._store

    def configure(self, user_id: str, provider: str, api_key: str) -> str:
        normalized = provider.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ProviderCredentialError(f"Unsupported provider: {provider}")
        self._store.set(user_id, normalized, api_key)
        return self._store.get(user_id, normalized).masked()

    def remove(self, user_id: str, provider: str) -> None:
        self._store.delete(user_id, provider)

    def configured(self, user_id: str) -> tuple[str, ...]:
        return self._store.configured_providers(user_id)

    def credential(self, user_id: str, provider: str) -> ProviderCredential:
        normalized = provider.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ProviderCredentialError(f"Unsupported provider: {provider}")
        return self._store.get(user_id, normalized)

    def generate(
        self,
        *,
        user_id: str,
        model: ModelSpec,
        input_items: list[Any],
        tools: list[Mapping[str, Any]] | None = None,
        tool_choice: str = "auto",
        transport: "BYOKHTTPTransport | None" = None,
        timeout_seconds: float = 30.0,
    ) -> ModelResponse:
        """Execute a provider request using the caller's own credential.

        BYOK generation is deliberately provider-agnostic and never returns the
        raw credential. Tool execution remains behind NEXUS's normal tool
        permission boundary; callers can pass an empty tool list for text-only
        BYOK generation.
        """
        request = build_byok_request(
            user_id=user_id,
            model=model,
            input_items=input_items,
            tools=tools or [],
            tool_choice=tool_choice,
            manager=self,
        )
        return (transport or BYOKHTTPTransport()).execute(request, timeout_seconds=timeout_seconds)


byok_provider_manager = BYOKProviderManager()


class BYOKProviderError(RuntimeError):
    """Raised when a provider request cannot be completed or parsed."""


class BYOKHTTPTransport:
    """Small real HTTPS transport with injectable opener for deterministic tests."""

    def __init__(self, opener: Callable[..., Any] = urlopen) -> None:
        self._opener = opener

    def execute(self, request: ProviderRequest, *, timeout_seconds: float = 30.0) -> ModelResponse:
        body = json.dumps(request.payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        http_request = Request(
            request.endpoint,
            data=body,
            headers=dict(request.headers),
            method="POST",
        )
        try:
            with self._opener(http_request, timeout=timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise BYOKProviderError(
                f"{request.provider} request failed with HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise BYOKProviderError(
                f"{request.provider} request failed: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise BYOKProviderError(f"{request.provider} request timed out") from exc

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BYOKProviderError(f"{request.provider} returned invalid JSON") from exc

        return self._parse_response(request, data)

    @staticmethod
    def _parse_response(request: ProviderRequest, data: Mapping[str, Any]) -> ModelResponse:
        provider = request.provider
        response_id = str(data.get("id", ""))
        output = ""

        tool_calls: list[Mapping[str, Any]] = []
        if provider == "openai":
            output = str(data.get("output_text", "") or "")
            for item in data.get("output", []) or []:
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") == "function_call":
                    tool_calls.append({
                        "name": str(item.get("name", "")),
                        "arguments": str(item.get("arguments", "{}")),
                        "call_id": str(item.get("call_id", "")),
                    })
                for content in item.get("content", []) or []:
                    if isinstance(content, Mapping) and content.get("text"):
                        output += str(content["text"])
        elif provider == "anthropic":
            chunks = []
            for item in data.get("content", []) or []:
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") == "tool_use":
                    tool_calls.append({
                        "name": str(item.get("name", "")),
                        "arguments": json.dumps(item.get("input", {}), separators=(",", ":")),
                        "call_id": str(item.get("id", "")),
                    })
                if item.get("text"):
                    chunks.append(str(item["text"]))
            output = "".join(chunks)
        else:
            choices = data.get("choices", []) or []
            if choices and isinstance(choices[0], Mapping):
                message = choices[0].get("message", {})
                if isinstance(message, Mapping):
                    if message.get("content"):
                        output = str(message["content"])
                    for call in message.get("tool_calls", []) or []:
                        if not isinstance(call, Mapping):
                            continue
                        function = call.get("function", {})
                        if isinstance(function, Mapping):
                            tool_calls.append({
                                "name": str(function.get("name", "")),
                                "arguments": str(function.get("arguments", "{}")),
                                "call_id": str(call.get("id", "")),
                            })

        if not output:
            raise BYOKProviderError(f"{provider} response did not contain text output")
        if not response_id:
            response_id = "provider-response"
        return ModelResponse(
            output=output,
            response_id=response_id,
            provider=provider,
            model_id=request.model_id,
            tool_calls=tuple(tool_calls),
        )


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    model_id: str
    endpoint: str
    headers: Mapping[str, str]
    payload: Mapping[str, Any]


class BYOKProviderAdapter:
    """Build provider requests from a user's credential.

    Network transport is injected so the model layer stays deterministic and
    unit-testable. Production API code can supply a real HTTPS transport.
    """

    provider: str
    endpoint: str

    def build_request(
        self,
        *,
        credential: ProviderCredential,
        model: ModelSpec,
        input_items: list[Any],
        tools: list[Mapping[str, Any]],
        tool_choice: str,
    ) -> ProviderRequest:
        raise NotImplementedError


class OpenAICompatibleBYOKAdapter(BYOKProviderAdapter):
    def __init__(self, provider: str, endpoint: str) -> None:
        self.provider = provider
        self.endpoint = endpoint

    def build_request(self, *, credential: ProviderCredential, model: ModelSpec,
                      input_items: list[Any], tools: list[Mapping[str, Any]],
                      tool_choice: str) -> ProviderRequest:
        headers = {
            "Authorization": f"Bearer {credential.key}",
            "Content-Type": "application/json",
        }
        if self.provider == "groq":
            payload: dict[str, Any] = {
                "model": model.model_id,
                "messages": input_items,
            }
        else:
            payload = {
                "model": model.model_id,
                "input": input_items,
            }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        return ProviderRequest(self.provider, model.model_id, self.endpoint, headers, payload)


class AnthropicBYOKAdapter(BYOKProviderAdapter):
    provider = "anthropic"
    endpoint = "https://api.anthropic.com/v1/messages"

    def build_request(self, *, credential: ProviderCredential, model: ModelSpec,
                      input_items: list[Any], tools: list[Mapping[str, Any]],
                      tool_choice: str) -> ProviderRequest:
        headers = {
            "x-api-key": credential.key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        messages = []
        for item in input_items:
            if isinstance(item, Mapping):
                messages.append(dict(item))
            else:
                messages.append({"role": "user", "content": str(item)})
        payload: dict[str, Any] = {
            "model": model.model_id,
            "max_tokens": 4096,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        return ProviderRequest(self.provider, model.model_id, self.endpoint, headers, payload)


BYOK_PROVIDER_ADAPTERS: dict[str, BYOKProviderAdapter] = {
    "openai": OpenAICompatibleBYOKAdapter("openai", "https://api.openai.com/v1/responses"),
    "groq": OpenAICompatibleBYOKAdapter("groq", "https://api.groq.com/openai/v1/chat/completions"),
    "anthropic": AnthropicBYOKAdapter(),
}


def provider_adapter(provider: str) -> BYOKProviderAdapter:
    normalized = provider.strip().lower()
    try:
        return BYOK_PROVIDER_ADAPTERS[normalized]
    except KeyError as exc:
        raise ProviderCredentialError(f"Unsupported provider: {provider}") from exc


def build_byok_request(
    *,
    user_id: str,
    model: ModelSpec,
    input_items: list[Any],
    tools: list[Mapping[str, Any]] | None = None,
    tool_choice: str = "auto",
    manager: BYOKProviderManager | None = None,
) -> ProviderRequest:
    owner = manager or byok_provider_manager
    credential = owner.credential(user_id, model.provider)
    return provider_adapter(model.provider).build_request(
        credential=credential,
        model=model,
        input_items=input_items,
        tools=tools or [],
        tool_choice=tool_choice,
    )
