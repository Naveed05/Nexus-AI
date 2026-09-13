from types import SimpleNamespace
from uuid import uuid4

from nexus.core.executor import ModelExecutor
from nexus.core.models import model_registry
from nexus.core.task import Task
from nexus.core.tools import ToolRegistry, ToolSpec


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)



def calculator_spec(risk_level: str = "low") -> ToolSpec:
    return ToolSpec(
        name="calculator",
        description="Calculate an expression.",
        input_schema={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
        risk_level=risk_level,
        handler=lambda expression: {"result": str(eval(expression, {"__builtins__": {}}, {}))},
    )


def knowledge_spec() -> ToolSpec:
    return ToolSpec(
        name="search_knowledge",
        description="Search workspace documents.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        risk_level="low",
        handler=lambda query: {
            "query": query,
            "results": [
                {
                    "chunk_id": str(uuid4()),
                    "document_id": str(uuid4()),
                    "text": "NEXUS uses hybrid retrieval.",
                    "citation": "architecture.md — chunk 1",
                }
            ],
            "context": "[Source: architecture.md — chunk 1]\nNEXUS uses hybrid retrieval.",
        },
    )


def test_executor_runs_function_tool_and_returns_final_output() -> None:
    registry = ToolRegistry()
    registry.register(calculator_spec())

    client = FakeClient(
        responses=[
            SimpleNamespace(
                id="resp_tool",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="calculator",
                        arguments='{"expression":"25 * 4"}',
                        call_id="calc_1",
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
    )
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


def test_executor_preserves_search_evidence_for_verification() -> None:
    registry = ToolRegistry()
    registry.register(knowledge_spec())
    client = FakeClient(
        responses=[
            SimpleNamespace(
                id="resp_research_tool",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="search_knowledge",
                        arguments='{"query":"hybrid retrieval"}',
                        call_id="research_1",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_research_final",
                output=[],
                output_text="NEXUS uses hybrid retrieval. [Source: architecture.md — chunk 1]",
            ),
        ]
    )
    executor = ModelExecutor(client=client, registry=registry)

    result = executor.execute(Task(objective="Research hybrid retrieval"), model_registry.get("astra"))

    assert result.output == "NEXUS uses hybrid retrieval. [Source: architecture.md — chunk 1]"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "search_knowledge"
    assert result.grounded_evidence
    assert result.grounded_evidence[0]["citation"] == "architecture.md — chunk 1"
    assert result.grounded_evidence[0]["text"] == "NEXUS uses hybrid retrieval."
