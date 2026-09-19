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

        if provider == "openai":
            output = str(data.get("output_text", "") or "")
            if not output:
                chunks: list[str] = []
                for item in data.get("output", []) or []:
                    if not isinstance(item, Mapping):
                        continue
                    for content in item.get("content", []) or []:
                        if isinstance(content, Mapping) and content.get("text"):
                            chunks.append(str(content["text"]))
                output = "".join(chunks)
        elif provider == "anthropic":
            chunks = []
            for item in data.get("content", []) or []:
                if isinstance(item, Mapping) and item.get("text"):
                    chunks.append(str(item["text"]))
            output = "".join(chunks)
        else:
            choices = data.get("choices", []) or []
            if choices and isinstance(choices[0], Mapping):
                message = choices[0].get("message", {})
                if isinstance(message, Mapping) and message.get("content"):
                    output = str(message["content"])

        if not output:
            raise BYOKProviderError(f"{provider} response did not contain text output")
        if not response_id:
            response_id = "provider-response"
        return ModelResponse(
            output=output,
            response_id=response_id,
            provider=provider,
            model_id=request.model_id,
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
