from __future__ import annotations
from dataclasses import dataclass
import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
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
        self.register(
            ModelSpec(
                key="groq-gpt-oss-120b",
                model_id="openai/gpt-oss-120b",
                provider="groq",
                tier="flagship",
                description="Groq-hosted GPT-OSS 120B for reasoning, coding, research, and agentic work.",
                capabilities=frozenset({"reasoning", "coding", "research", "agentic", "tools", "data_analysis", "document_analysis"}),
                reasoning_levels=frozenset({"low", "medium", "high", "max"}),
                context_window=131_072,
                supports_tools=True,
                cost_score=4,
                latency_score=2,
            )
        )
        self.register(
            ModelSpec(
                key="groq-gpt-oss-20b",
                model_id="openai/gpt-oss-20b",
                provider="groq",
                tier="professional",
                description="Groq-hosted GPT-OSS 20B for fast general workloads.",
                capabilities=frozenset({"reasoning", "coding", "research", "agentic", "tools", "data_analysis", "document_analysis"}),
                reasoning_levels=frozenset({"low", "medium", "high", "max"}),
                context_window=131_072,
                supports_tools=True,
                cost_score=2,
                latency_score=1,
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

GROQ_MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        key="groq-gpt-oss-120b",
        model_id="openai/gpt-oss-120b",
        provider="groq",
        tier="flagship",
        description="Groq-hosted GPT-OSS 120B.",
        capabilities=frozenset({"reasoning", "coding", "research", "agentic", "tools", "data_analysis", "document_analysis"}),
        reasoning_levels=frozenset({"low", "medium", "high", "max"}),
        context_window=131_072,
        supports_tools=True,
        cost_score=4,
        latency_score=2,
    ),
    ModelSpec(
        key="groq-gpt-oss-20b",
        model_id="openai/gpt-oss-20b",
        provider="groq",
        tier="professional",
        description="Groq-hosted GPT-OSS 20B.",
        capabilities=frozenset({"reasoning", "coding", "research", "agentic", "tools", "data_analysis", "document_analysis"}),
        reasoning_levels=frozenset({"low", "medium", "high", "max"}),
        context_window=131_072,
        supports_tools=True,
        cost_score=2,
        latency_score=1,
    ),
)

def provider_model_specs(provider: str) -> tuple[ModelSpec, ...]:
    normalized = provider.strip().lower()
    if normalized == "groq":
        return GROQ_MODEL_SPECS
    return tuple(model for model in model_registry.all() if model.provider == normalized)


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


class PersistentCredentialStore:
    """Small durable credential store for the local single-instance deployment.

    Values are encrypted with a Fernet key stored outside the database. The key
    can be supplied with NEXUS_CREDENTIAL_ENCRYPTION_KEY; otherwise a local key
    file is generated under .nexus. This is intended for the local runtime, not
    as a substitute for a managed production secret store.
    """

    def __init__(self, storage_path: str | Path = ".nexus/credentials.sqlite3") -> None:
        from cryptography.fernet import Fernet
        self._fernet = None
        self._path = Path(storage_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        raw_key = os.getenv("NEXUS_CREDENTIAL_ENCRYPTION_KEY", "").strip()
        key_path = Path(os.getenv("NEXUS_CREDENTIAL_KEY_PATH", ".nexus/credentials.key"))
        if raw_key:
            key = raw_key.encode("utf-8")
        else:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            if key_path.exists():
                key = key_path.read_bytes().strip()
            else:
                key = Fernet.generate_key()
                key_path.write_bytes(key)
                try:
                    os.chmod(key_path, 0o600)
                except OSError:
                    pass
        self._fernet = Fernet(key)
        self._lock = RLock()
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS credentials (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                secret BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, provider)
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS preferences (
                user_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self._connection.commit()

    def set(self, user_id: str, provider: str, api_key: str) -> None:
        if not user_id.strip():
            raise ProviderCredentialError("user_id cannot be empty")
        credential = ProviderCredential(provider=provider.strip().lower(), key=api_key.strip())
        encrypted = self._fernet.encrypt(credential.key.encode("utf-8"))
        with self._lock:
            self._connection.execute(
                "INSERT OR REPLACE INTO credentials(user_id,provider,secret,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",
                (user_id.strip(), credential.provider, encrypted),
            )
            self._connection.execute(
                "INSERT OR REPLACE INTO preferences(user_id,provider,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)",
                (user_id.strip(), credential.provider),
            )
            self._connection.commit()

    def get(self, user_id: str, provider: str) -> ProviderCredential:
        normalized = provider.strip().lower()
        with self._lock:
            row = self._connection.execute(
                "SELECT secret FROM credentials WHERE user_id=? AND provider=?",
                (user_id.strip(), normalized),
            ).fetchone()
        if not row:
            raise ProviderNotConfiguredError(f"No API key configured for provider: {normalized}")
        try:
            secret = self._fernet.decrypt(bytes(row[0])).decode("utf-8")
        except Exception as exc:
            raise ProviderCredentialError("stored provider credential could not be decrypted") from exc
        return ProviderCredential(provider=normalized, key=secret)

    def delete(self, user_id: str, provider: str) -> None:
        normalized = provider.strip().lower()
        with self._lock:
            self._connection.execute(
                "DELETE FROM credentials WHERE user_id=? AND provider=?",
                (user_id.strip(), normalized),
            )
            self._connection.execute(
                "DELETE FROM preferences WHERE user_id=? AND provider=?",
                (user_id.strip(), normalized),
            )
            self._connection.commit()

    def configured_providers(self, user_id: str) -> tuple[str, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT provider FROM credentials WHERE user_id=? ORDER BY provider",
                (user_id.strip(),),
            ).fetchall()
        return tuple(row[0] for row in rows)

    def preferred(self, user_id: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT provider FROM preferences WHERE user_id=?",
                (user_id.strip(),),
            ).fetchone()
        return row[0] if row else None


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
        self._store = credential_store or PersistentCredentialStore()
        self._preferred_provider: dict[str, str] = {}

    @property
    def credential_store(self) -> InMemoryCredentialStore:
        return self._store

    def configure(self, user_id: str, provider: str, api_key: str) -> str:
        normalized = provider.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ProviderCredentialError(f"Unsupported provider: {provider}")
        self._store.set(user_id, normalized, api_key)
        self._preferred_provider[user_id.strip()] = normalized
        return self._store.get(user_id, normalized).masked()

    def remove(self, user_id: str, provider: str) -> None:
        normalized = provider.strip().lower()
        self._store.delete(user_id, normalized)
        if self._preferred_provider.get(user_id.strip()) == normalized:
            remaining = self.configured(user_id)
            if remaining:
                self._preferred_provider[user_id.strip()] = remaining[0]
            else:
                self._preferred_provider.pop(user_id.strip(), None)

    def configured(self, user_id: str) -> tuple[str, ...]:
        return self._store.configured_providers(user_id)

    def preferred(self, user_id: str) -> str | None:
        """Return the most recently configured provider for this local user."""
        stored = getattr(self._store, "preferred", lambda _user: None)(user_id)
        return stored or self._preferred_provider.get(user_id.strip())

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
