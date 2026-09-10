import pytest

from nexus.core.tools import calculator, tool_registry


def test_calculator() -> None:
    assert calculator("(25 * 4) + 10")["result"] == "110"


def test_calculator_rejects_unsupported_characters() -> None:
    with pytest.raises(ValueError):
        calculator("__import__('os').getcwd()")


def test_registry_exposes_openai_tool_schema() -> None:
    tools = tool_registry.openai_tools()
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["name"] == "calculator"
    assert tools[0]["strict"] is True
