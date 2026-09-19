import pytest

from nexus.core.models import BYOKProviderManager, ProviderCredentialError, ProviderNotConfiguredError
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
