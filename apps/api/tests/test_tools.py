import pytest

from nexus.core.data_engine import DataIntelligenceEngine
from nexus.core.tools import calculator, tool_registry


def test_calculator() -> None:
    assert calculator("(25 * 4) + 10")["result"] == "110"


def test_calculator_rejects_unsupported_characters() -> None:
    with pytest.raises(ValueError):
        calculator("__import__('os').getcwd()")


def test_registry_exposes_openai_tool_schema() -> None:
    tools = tool_registry.openai_tools()
    assert len(tools) == 2
    assert {tool["name"] for tool in tools} == {"calculator", "profile_dataset"}
    assert all(tool["type"] == "function" for tool in tools)
    assert all(tool["strict"] is True for tool in tools)


def test_profile_dataset_tool_matches_engine() -> None:
    tool = tool_registry.get("profile_dataset")
    result = tool.handler("name,score\nA,10\nB,\n")

    assert result["profile"]["rows"] == 2
    assert result["profile"]["columns"] == 2
    assert result["quality"]["quality_flags"]["has_missing_values"] is True
