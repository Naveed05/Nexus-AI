from types import SimpleNamespace

import pytest

from nexus.core.executor import ModelExecutor
from nexus.core.models import model_registry
from nexus.core.task import Task
from nexus.core.tools import ToolRegistry, ToolSpec


class FakeResponses:
    def __init__(self, responses=None) -> None:
        self.calls: list[dict] = []
        self.responses = responses or [
            SimpleNamespace(
                id="resp_tool",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="calculator",
                        arguments='{"expression":"25 * 4"}',
                        call_id="call_1",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_final",
                output=[],
                output_text="The answer is 100.",
            ),
        ]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses=None) -> None:
        self.responses = FakeResponses(responses)


def calculator_spec(risk_level: str = "low") -> ToolSpec:
    return ToolSpec(
        name="calculator",
        description="Perform arithmetic.",
        input_schema={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
        risk_level=risk_level,
        handler=lambda expression: {"result": str(eval(expression, {"__builtins__": {}}, {}))},
    )


def test_executor_runs_function_tool_and_returns_final_output() -> None:
    registry = ToolRegistry()
    registry.register(calculator_spec())

    client = FakeClient()
    executor = ModelExecutor(client=client, registry=registry)
    task = Task(objective="Calculate 25 times 4")
    model = model_registry.get("astra")

    result = executor.execute(task, model)

    assert result.output == "The answer is 100."
    assert result.response_id == "resp_final"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "calculator"
    assert result.tool_calls[0].arguments == {"expression": "25 * 4"}
    assert result.tool_calls[0].result == {"result": "100"}
    assert result.tool_calls[0].success is True
    assert len(client.responses.calls) == 2

    second_input = client.responses.calls[1]["input"]
    assert any(item["type"] == "function_call_output" for item in second_input if isinstance(item, dict))


def test_executor_enforces_allowed_tool_list() -> None:
    registry = ToolRegistry()
    registry.register(calculator_spec())
    client = FakeClient()
    executor = ModelExecutor(client=client, registry=registry)

    result = executor.execute(
        Task(objective="Do not use tools"),
        model_registry.get("astra"),
        allowed_tools=(),
    )

    assert result.output == "The answer is 100."
    assert client.responses.calls[0]["tools"] == []
    assert client.responses.calls[0]["tool_choice"] == "none"


def test_executor_stops_on_approval_required_tool() -> None:
    registry = ToolRegistry()
    registry.register(calculator_spec(risk_level="medium"))
    client = FakeClient()
    executor = ModelExecutor(client=client, registry=registry)

    with pytest.raises(PermissionError, match="requires explicit user approval"):
        executor.execute(
            Task(objective="Calculate something"),
            model_registry.get("astra"),
        )

    assert len(client.responses.calls) == 1
