import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from nexus.core.config import settings
from nexus.core.models import ModelSpec
from nexus.core.task import RiskLevel, Task
from nexus.core.tools import ToolRegistry, ToolSpec, tool_registry


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    risk_level: str = "low"
    permission: str = "read"


@dataclass(frozen=True)
class ExecutionResult:
    model_key: str
    model_id: str
    response_id: str
    output: str
    tool_calls: tuple[ToolCallRecord, ...] = ()


class ToolPermissionPolicy:
    """Controls which registered tools a task is allowed to execute."""

    _risk_rank = {"low": 0, "medium": 1, "high": 2}
    _permission_rank = {"read": 0, "modify": 1, "high_risk": 2}

    def authorize(self, task: Task, tool: ToolSpec) -> None:
        if self._risk_rank[tool.risk_level] > self._risk_rank[task.risk_level.value]:
            raise PermissionError(
                f"Tool '{tool.name}' requires {tool.risk_level} risk authorization."
            )
        if tool.permission == "high_risk" and task.risk_level != RiskLevel.HIGH:
            raise PermissionError(
                f"Tool '{tool.name}' requires explicit high-risk task authorization."
            )
        if self._permission_rank[tool.permission] >= 2 and task.risk_level != RiskLevel.HIGH:
            raise PermissionError(
                f"Tool '{tool.name}' is blocked by the NEXUS permission policy."
            )


class ModelExecutor:
    """Executes routed NEXUS tasks through the Responses API and local tools."""

    def __init__(
        self,
        client: OpenAI | None = None,
        registry: ToolRegistry | None = None,
        policy: ToolPermissionPolicy | None = None,
        max_tool_rounds: int = 8,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be at least 1")
        self._client = client
        self._registry = registry or tool_registry
        self._policy = policy or ToolPermissionPolicy()
        self._max_tool_rounds = max_tool_rounds

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def execute(self, task: Task, model: ModelSpec) -> ExecutionResult:
        client = self._get_client()
        tools = self._registry.openai_tools()
        input_items: list[Any] = [task.objective]
        tool_calls: list[ToolCallRecord] = []
        tool_rounds = 0

        while True:
            response = client.responses.create(
                model=model.model_id,
                input=input_items,
                tools=tools,
                tool_choice="auto",
            )

            function_calls = [
                item for item in response.output if item.type == "function_call"
            ]
            if not function_calls:
                return ExecutionResult(
                    model_key=model.key,
                    model_id=model.model_id,
                    response_id=response.id,
                    output=response.output_text,
                    tool_calls=tuple(tool_calls),
                )

            if tool_rounds >= self._max_tool_rounds:
                raise RuntimeError("NEXUS tool execution limit exceeded")
            tool_rounds += 1

            input_items.extend(response.output)
            tool_outputs: list[dict[str, Any]] = []

            for call in function_calls:
                arguments = json.loads(call.arguments)
                tool = self._registry.get(call.name)

                try:
                    self._policy.authorize(task, tool)
                    result = tool.handler(**arguments)
                except Exception as exc:
                    result = {"error": str(exc), "tool": call.name}

                tool_calls.append(
                    ToolCallRecord(
                        tool_name=call.name,
                        arguments=arguments,
                        result=result,
                        risk_level=tool.risk_level,
                        permission=tool.permission,
                    )
                )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result),
                    }
                )

            input_items.extend(tool_outputs)
