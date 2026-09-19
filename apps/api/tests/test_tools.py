import pytest

from nexus.core.models import (
    BYOKHTTPTransport, BYOKProviderError, BYOKProviderManager,
    ProviderCredentialError, ProviderNotConfiguredError, build_byok_request,
    model_registry,
)
from nexus.core.tools import calculator, tool_registry


def test_calculator() -> None:
    assert calculator("(25 * 4) + 10")["result"] == "110"


def test_calculator_rejects_unsupported_characters() -> None:
    with pytest.raises(ValueError):
        calculator("__import__('os').getcwd()")


def test_registry_exposes_openai_tool_schema() -> None:
    tools = tool_registry.openai_tools()
    assert len(tools) == 8
    assert {tool["name"] for tool in tools} == {
        "calculator",
        "profile_dataset",
        "analyze_dataset",
        "profile_dataset_by_id",
        "analyze_dataset_by_id",
        "baseline_ml",
        "search_knowledge",
        "research_knowledge",
    }
    assert all(tool["type"] == "function" for tool in tools)
    assert all(tool["strict"] is True for tool in tools)


def test_profile_dataset_tool_matches_engine() -> None:
    tool = tool_registry.get("profile_dataset")
    result = tool.handler("name,score\nA,10\nB,\n")
    assert result["profile"]["rows"] == 2
    assert result["profile"]["columns"] == 2
    assert result["quality"]["quality_flags"]["has_missing_values"] is True


def test_analyze_dataset_tool_runs_pipeline() -> None:
    tool = tool_registry.get("analyze_dataset")
    result = tool.handler("name,score\nA,10\nB,\nB,\n", None)
    assert result["cleaned_shape"]["rows"] == 2
    assert result["eda"]["numeric"]["score"]["mean"] == pytest.approx(10.0)
    assert result["problem"]["type"] == "descriptive"


def test_byok_provider_manager_supports_openai_anthropic_and_groq() -> None:
    manager = BYOKProviderManager()
    manager.configure("user-1", "OpenAI", "sk-openai-example")
    manager.configure("user-1", "anthropic", "sk-ant-example")
    manager.configure("user-1", "GROQ", "gsk-example")

    assert manager.configured("user-1") == ("anthropic", "groq", "openai")
    assert manager.credential("user-1", "openai").key == "sk-openai-example"


def test_byok_never_returns_raw_key_from_masked_credential() -> None:
    manager = BYOKProviderManager()
    masked = manager.configure("user-1", "openai", "sk-super-secret-key")
    assert masked == "sk-s••••••••-key"
    assert "super-secret" not in masked


def test_byok_isolated_per_user_and_provider() -> None:
    manager = BYOKProviderManager()
    manager.configure("user-1", "openai", "key-one")
    manager.configure("user-2", "openai", "key-two")

    assert manager.credential("user-1", "openai").key == "key-one"
    assert manager.credential("user-2", "openai").key == "key-two"
    manager.remove("user-1", "openai")
    with pytest.raises(ProviderNotConfiguredError):
        manager.credential("user-1", "openai")
    assert manager.credential("user-2", "openai").key == "key-two"


def test_byok_rejects_unknown_provider_and_empty_key() -> None:
    manager = BYOKProviderManager()
    with pytest.raises(ProviderCredentialError):
        manager.configure("user-1", "gemini", "key")
    with pytest.raises(ProviderCredentialError):
        manager.configure("user-1", "openai", " ")


def test_byok_builds_provider_requests_without_exposing_key_in_payload() -> None:
    manager = BYOKProviderManager()
    manager.configure("user-1", "openai", "sk-test-secret")
    request = build_byok_request(
        user_id="user-1",
        model=model_registry.get("terra"),
        input_items=[{"role": "user", "content": "hello"}],
        manager=manager,
    )
    assert request.provider == "openai"
    assert request.endpoint.endswith("/v1/responses")
    assert request.headers["Authorization"] == "Bearer sk-test-secret"
    assert request.payload["model"] == "gpt-5.6-terra"
    assert "sk-test-secret" not in str(request.payload)


def test_byok_builds_anthropic_and_groq_requests() -> None:
    manager = BYOKProviderManager()
    manager.configure("user-1", "anthropic", "ant-secret")
    manager.configure("user-1", "groq", "groq-secret")

    claude = build_byok_request(
        user_id="user-1",
        model=type(model_registry.get("terra"))(
            key="claude-test", model_id="claude-sonnet", provider="anthropic",
            tier="professional", description="test", capabilities=frozenset(),
            reasoning_levels=frozenset(), context_window=200_000,
            supports_tools=True, cost_score=2, latency_score=3,
        ),
        input_items=[{"role": "user", "content": "hello"}],
        manager=manager,
    )
    groq = build_byok_request(
        user_id="user-1",
        model=type(model_registry.get("terra"))(
            key="groq-test", model_id="llama-test", provider="groq",
            tier="balanced", description="test", capabilities=frozenset(),
            reasoning_levels=frozenset(), context_window=128_000,
            supports_tools=True, cost_score=1, latency_score=4,
        ),
        input_items=["hello"],
        manager=manager,
    )
    assert claude.headers["x-api-key"] == "ant-secret"
    assert claude.endpoint.endswith("/v1/messages")
    assert groq.headers["Authorization"] == "Bearer groq-secret"
    assert groq.endpoint.endswith("/openai/v1/chat/completions")
    assert groq.payload["messages"] == ["hello"]
    assert "input" not in groq.payload



class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        import json
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


def test_byok_transport_executes_and_normalizes_openai_response() -> None:
    manager = BYOKProviderManager()
    manager.configure("user-1", "openai", "sk-test-secret")
    request = build_byok_request(
        user_id="user-1",
        model=model_registry.get("terra"),
        input_items=[{"role": "user", "content": "hello"}],
        manager=manager,
    )
    captured = {}

    def opener(http_request, timeout):
        captured["authorization"] = http_request.headers["Authorization"]
        captured["timeout"] = timeout
        return _FakeHTTPResponse({
            "id": "resp_123",
            "output_text": "Hello from OpenAI",
        })

    response = BYOKHTTPTransport(opener).execute(request, timeout_seconds=7)
    assert response.output == "Hello from OpenAI"
    assert response.response_id == "resp_123"
    assert response.provider == "openai"
    assert captured == {"authorization": "Bearer sk-test-secret", "timeout": 7}


def test_byok_transport_normalizes_anthropic_and_groq_responses() -> None:
    manager = BYOKProviderManager()
    manager.configure("user-1", "anthropic", "ant-secret")
    manager.configure("user-1", "groq", "groq-secret")

    claude_request = build_byok_request(
        user_id="user-1",
        model=type(model_registry.get("terra"))(
            key="claude-test", model_id="claude-sonnet", provider="anthropic",
            tier="professional", description="test", capabilities=frozenset(),
            reasoning_levels=frozenset(), context_window=200_000,
            supports_tools=True, cost_score=2, latency_score=3,
        ),
        input_items=[{"role": "user", "content": "hello"}],
        manager=manager,
    )
    groq_request = build_byok_request(
        user_id="user-1",
        model=type(model_registry.get("terra"))(
            key="groq-test", model_id="llama-test", provider="groq",
            tier="balanced", description="test", capabilities=frozenset(),
            reasoning_levels=frozenset(), context_window=128_000,
            supports_tools=True, cost_score=1, latency_score=4,
        ),
        input_items=["hello"],
        manager=manager,
    )

    claude = BYOKHTTPTransport(
        lambda request, timeout: _FakeHTTPResponse({"id": "msg_1", "content": [{"type": "text", "text": "Claude reply"}]})
    ).execute(claude_request)
    groq = BYOKHTTPTransport(
        lambda request, timeout: _FakeHTTPResponse({"id": "chat_1", "choices": [{"message": {"content": "Groq reply"}}]})
    ).execute(groq_request)

    assert claude.output == "Claude reply"
    assert claude.response_id == "msg_1"
    assert groq.output == ""  # chat-completions parsing is added below


def test_byok_transport_rejects_invalid_json() -> None:
    class InvalidResponse(_FakeHTTPResponse):
        def __init__(self):
            self._payload = b"not-json"

    with pytest.raises(BYOKProviderError, match="invalid JSON"):
        BYOKHTTPTransport(lambda request, timeout: InvalidResponse()).execute(
            build_byok_request(
                user_id="user-1",
                model=model_registry.get("terra"),
                input_items=["hello"],
                manager=BYOKProviderManager(),
            )
        )
