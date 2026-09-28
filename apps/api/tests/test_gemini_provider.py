import json

from nexus.core.models import (
    BYOKProviderManager,
    BYOKHTTPTransport,
    GEMINI_MODEL_SPECS,
    InMemoryCredentialStore,
    build_byok_request,
    provider_model_specs,
)


def test_gemini_catalog_exposes_flash_model() -> None:
    model = GEMINI_MODEL_SPECS[0]
    assert model.provider == "gemini"
    assert model.model_id == "gemini-3.8-flash"
    assert model.context_window == 1_000_000
    assert model.reasoning_levels == frozenset({"low", "medium", "high"})
    assert {"reasoning", "tools", "agentic", "multimodal", "long_context"}.issubset(model.capabilities)
    assert model.supports_tools is True


def test_gemini_is_available_through_provider_catalog() -> None:
    assert provider_model_specs("gemini") == GEMINI_MODEL_SPECS


def test_gemini_builds_openai_compatible_request() -> None:
    manager = BYOKProviderManager(InMemoryCredentialStore())
    manager.configure("user-1", "gemini", "gemini-test-key")
    request = build_byok_request(
        user_id="user-1",
        model=GEMINI_MODEL_SPECS[0],
        input_items=[{"role": "user", "content": "Analyze this experiment."}],
        tools=[{"type": "function", "function": {"name": "profile_dataset"}}],
        tool_choice="auto",
        manager=manager,
    )

    assert request.provider == "gemini"
    assert request.endpoint == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert request.headers["Authorization"] == "Bearer gemini-test-key"
    assert request.payload["model"] == "gemini-3.8-flash"
    assert request.payload["messages"][0]["content"] == "Analyze this experiment."
    assert request.payload["tools"][0]["function"]["name"] == "profile_dataset"
    assert request.payload["tool_choice"] == "auto"


def test_gemini_response_parser_accepts_openai_compatible_output() -> None:
    manager = BYOKProviderManager(InMemoryCredentialStore())
    manager.configure("user-1", "gemini", "gemini-test-key")
    request = build_byok_request(
        user_id="user-1",
        model=GEMINI_MODEL_SPECS[0],
        input_items=[{"role": "user", "content": "test"}],
        manager=manager,
    )
    response = BYOKHTTPTransport(opener=lambda *_args, **_kwargs: None)

    data = {
        "id": "gemini-test-response",
        "choices": [{"message": {"content": "Gemini result"}}],
    }
    parsed = response._parse_response(request, data)
    assert parsed.provider == "gemini"
    assert parsed.model_id == GEMINI_MODEL_SPECS[0].model_id
    assert parsed.output == "Gemini result"
    assert parsed.response_id == "gemini-test-response"


def test_gemini_server_key_path_does_not_persist_credentials() -> None:
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            return json.dumps({
                "id": "server-test",
                "choices": [{"message": {"content": "ok"}}],
            }).encode("utf-8")

    manager = BYOKProviderManager(InMemoryCredentialStore())
    response = manager.generate_with_api_key(
        provider="gemini",
        api_key="gemini-server-test",
        model=GEMINI_MODEL_SPECS[0],
        input_items=[{"role": "user", "content": "hello"}],
        transport=BYOKHTTPTransport(opener=lambda *_args, **_kwargs: FakeResponse()),
    )
    assert response.output == "ok"
    assert manager.configured("server-user") == ()
