import pytest

from nexus.core.tools import calculator, tool_registry


def test_calculator() -> None:
    assert calculator("(25 * 4) + 10")["result"] == "110"


def test_calculator_rejects_unsupported_characters() -> None:
    with pytest.raises(ValueError):
        calculator("__import__('os').getcwd()")


def test_registry_exposes_openai_tool_schema() -> None:
    tools = tool_registry.openai_tools()
    assert len(tools) == 6
    assert {tool["name"] for tool in tools} == {
        "calculator",
        "profile_dataset",
        "analyze_dataset",
        "profile_dataset_by_id",
        "analyze_dataset_by_id",
        "baseline_ml",
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
