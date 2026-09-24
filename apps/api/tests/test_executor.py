from types import SimpleNamespace
from uuid import uuid4

import pytest

from nexus.core.executor import ModelExecutor
from nexus.core.models import model_registry
from nexus.core.task import RiskLevel, Task
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


def research_spec() -> ToolSpec:
    return ToolSpec(
        name="research_knowledge",
        description="Research workspace knowledge.",
        input_schema={
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
            "additionalProperties": False,
        },
        risk_level="low",
        handler=lambda question: {
            "question": question,
            "sources": [
                {
                    "chunk_id": str(uuid4()),
                    "document_id": str(uuid4()),
                    "text": "Research evidence supports the claim.",
                    "citation": "research.md — chunk 2",
                    "query": question,
                }
            ],
            "synthesis": {
                "context": "[Source: research.md — chunk 2]\nResearch evidence supports the claim."
            },
        },
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

    first_input = client.responses.calls[0]["input"]
    assert first_input[0] == {"role": "user", "content": "Calculate 25 times 4"}

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

    assert len(result.grounded_evidence) == 1
    assert result.grounded_evidence[0]["citation"] == "architecture.md — chunk 1"
    assert result.grounded_evidence[0]["text"] == "NEXUS uses hybrid retrieval."
    assert "architecture.md — chunk 1" in result.output


def test_executor_preserves_research_tool_evidence_for_verification() -> None:
    registry = ToolRegistry()
    registry.register(research_spec())
    client = FakeClient(
        responses=[
            SimpleNamespace(
                id="resp_research_tool",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="research_knowledge",
                        arguments='{"question":"NEXUS verification"}',
                        call_id="research_2",
                    )
                ],
                output_text="",
            ),
            SimpleNamespace(
                id="resp_research_final",
                output=[],
                output_text="Research evidence supports the claim. [Source: research.md — chunk 2]",
            ),
        ]
    )
    executor = ModelExecutor(client=client, registry=registry)

    result = executor.execute(Task(objective="Research NEXUS verification"), model_registry.get("astra"))

    assert len(result.grounded_evidence) == 1
    assert result.grounded_evidence[0]["citation"] == "research.md — chunk 2"
    assert result.grounded_evidence[0]["text"] == "Research evidence supports the claim."
    assert result.grounded_evidence[0]["query"] == "NEXUS verification"


def test_executor_enforces_allowed_tool_list() -> None:
    registry = ToolRegistry()
    registry.register(calculator_spec())
    client = FakeClient(
        responses=[
            SimpleNamespace(id="resp_final", output=[], output_text="No tool used.")
        ]
    )
    executor = ModelExecutor(client=client, registry=registry)

    result = executor.execute(
        Task(objective="Do not use tools"),
        model_registry.get("astra"),
        allowed_tools=(),
    )

    assert result.output == "No tool used."
    assert client.responses.calls[0]["tools"] == []
    assert client.responses.calls[0]["tool_choice"] == "none"


def test_executor_stops_on_approval_required_tool() -> None:
    registry = ToolRegistry()
    registry.register(calculator_spec(risk_level="medium"))
    client = FakeClient()
    executor = ModelExecutor(client=client, registry=registry)

    with pytest.raises(PermissionError, match="requires explicit user approval"):
        executor.execute(
            Task(objective="Calculate something", risk_level=RiskLevel.MEDIUM),
            model_registry.get("astra"),
        )

    assert len(client.responses.calls) == 1


def test_executor_uses_central_tool_execution_boundary() -> None:
    registry = ToolRegistry()
    registry.register(calculator_spec())

    class Boundary:
        def __init__(self) -> None:
            self.calls = []

        def execute(self, task, tool_name, arguments):
            from nexus.core.permissions import PermissionDecision
            self.calls.append((task.task_id, tool_name, arguments))
            return SimpleNamespace(
                permission=PermissionDecision.ALLOW,
                success=True,
                output={"result": "boundary"},
                error=None,
            )

    boundary = Boundary()
    client = FakeClient()
    executor = ModelExecutor(client=client, registry=registry, execution_boundary=boundary)

    result = executor.execute(Task(objective="Calculate"), model_registry.get("astra"))

    assert result.tool_calls[0].result == {"result": "boundary"}
    assert boundary.calls[0][1] == "calculator"


def test_executor_uses_canonical_boundary_for_builtin_registry() -> None:
    from nexus.core.executor import tool_executor

    executor = ModelExecutor(client=FakeClient())
    assert executor._execution_boundary is tool_executor


def test_provider_registry_supports_custom_provider() -> None:
    from nexus.core.executor import ModelProviderRegistry
    from nexus.core.models import ModelResponse

    class Provider:
        name = "custom"

        def generate(self, **kwargs):
            return ModelResponse("custom output", "custom-1", "custom", kwargs["model"].model_id)

    registry = ModelProviderRegistry({"custom": Provider()})
    provider = registry.get("custom")
    assert provider.generate(model=model_registry.get("terra"), input_items=[], tools=[], tool_choice="none").output == "custom output"


def test_executor_falls_back_across_prevalidated_models() -> None:
    from nexus.core.executor import ModelProviderRegistry, ModelProviderExecutionError
    from nexus.core.frontier_workflows import FrontierWorkflowPlan
    from nexus.core.models import ModelResponse

    class SequenceProvider:
        name = "openai"

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ModelProviderExecutionError("temporary provider outage")
            return ModelResponse("fallback success", "resp-fallback", "openai", kwargs["model"].model_id)

    provider = SequenceProvider()
    registry = ModelProviderRegistry({"openai": provider})
    executor = ModelExecutor(client=FakeClient(), provider_registry=registry)
    plan = FrontierWorkflowPlan(
        primary=model_registry.get("astra"),
        fallbacks=(model_registry.get("sol"),),
        required_capabilities=frozenset(),
        reasoning_level="medium",
    )

    result = executor.execute_with_fallback(Task(objective="Recover from provider outage"), plan)

    assert result.model_key == "sol"
    assert result.output == "fallback success"
    assert result.fallback_count == 1
    assert result.fallback_history[0].startswith("astra->sol:")
    assert provider.calls == 2
