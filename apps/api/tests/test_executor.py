from types import SimpleNamespace

from nexus.core.executor import ModelExecutor
from nexus.core.models import model_registry
from nexus.core.task import Task
from nexus.core.tools import ToolRegistry, ToolSpec


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.responses = [
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
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_executor_runs_function_tool_and_returns_final_output() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="calculator",
            description="Perform arithmetic.",
            input_schema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
                "additionalProperties": False,
            },
            risk_level="low",
            handler=lambda expression: {"result": str(eval(expression, {"__builtins__": {}}, {}))},
        )
    )

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
    assert len(client.responses.calls) == 2

    second_input = client.responses.calls[1]["input"]
    assert any(item["type"] == "function_call_output" for item in second_input if isinstance(item, dict))
