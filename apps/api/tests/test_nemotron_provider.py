import json

from nexus.core.models import (
    BYOKProviderManager,
    BYOKHTTPTransport,
    InMemoryCredentialStore,
    NEMOTRON_MODEL_SPECS,
    build_byok_request,
    provider_model_specs,
)
from nexus.core.router import TaskRouter
from nexus.core.task import Task


def test_nemotron_catalog_exposes_long_context_reasoning_model() -> None:
    model = NEMOTRON_MODEL_SPECS[0]
    assert model.provider == "nemotron"
    assert model.model_id == "nvidia/nemotron-3-super-120b-a12b"
    assert model.context_window == 1_000_000
    assert model.reasoning_levels == frozenset({"none", "low", "high"})
    assert {"reasoning", "tools", "agentic", "long_context"}.issubset(model.capabilities)
    assert model.supports_tools is True


def test_nemotron_is_available_through_provider_catalog() -> None:
    assert provider_model_specs("nemotron") == NEMOTRON_MODEL_SPECS


def test_router_can_target_nemotron_explicitly() -> None:
    decision = TaskRouter().decide(
        Task(objective="Research and reason through this multi-step data problem"),
        provider="nemotron",
    )
    assert decision.model.provider == "nemotron"
    assert decision.model.context_window == 1_000_000


def test_nemotron_builds_openai_compatible_reasoning_request() -> None:
    manager = BYOKProviderManager(InMemoryCredentialStore())
    manager.configure("user-1", "nemotron", "nvapi-test-key")
    request = build_byok_request(
        user_id="user-1",
        model=NEMOTRON_MODEL_SPECS[0],
        input_items=[{"role": "user", "content": "Analyze this experiment."}],
        tools=[{"type": "function", "function": {"name": "profile_dataset"}}],
        tool_choice="auto",
        manager=manager,
    )

    assert request.provider == "nemotron"
    assert request.endpoint == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer nvapi-test-key"
    assert request.payload["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert request.payload["messages"][0]["content"] == "Analyze this experiment."
    assert request.payload["tools"][0]["function"]["name"] == "profile_dataset"
    assert request.payload["tool_choice"] == "auto"
    assert request.payload["temperature"] == 1.0
    assert request.payload["top_p"] == 0.95
    assert request.payload["max_tokens"] == 16_384
    assert request.payload["reasoning_effort"] == "high"


def test_nemotron_response_parser_accepts_openai_compatible_output() -> None:
    manager = BYOKProviderManager(InMemoryCredentialStore())
    manager.configure("user-1", "nemotron", "nvapi-test-key")
    request = build_byok_request(
        user_id="user-1",
        model=NEMOTRON_MODEL_SPECS[0],
        input_items=[{"role": "user", "content": "test"}],
        manager=manager,
    )
    response = BYOKHTTPTransport(opener=lambda *_args, **_kwargs: None)

    data = {
        "id": "nemotron-test-response",
        "choices": [{"message": {"content": "Evidence-backed result"}}],
    }
    parsed = response._parse_response(request, data)
    assert parsed.provider == "nemotron"
    assert parsed.model_id == NEMOTRON_MODEL_SPECS[0].model_id
    assert parsed.output == "Evidence-backed result"
    assert parsed.response_id == "nemotron-test-response"
