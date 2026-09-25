import json
import time
from dataclasses import dataclass
from typing import Any, Mapping

from openai import OpenAI

from nexus.core.config import settings
from nexus.core.frontier_workflows import FrontierWorkflowPlan, FallbackReason, FrontierFallbackController
from nexus.core.knowledge import reset_knowledge_workspace, set_knowledge_workspace
from nexus.core.models import (
    BYOKProviderError,
    BYOKProviderManager,
    ModelResponse,
    ModelSpec,
    byok_provider_manager,
    model_health_registry,
)
from nexus.core.permissions import PermissionDecision, PermissionPolicy
from nexus.core.task import Task
from nexus.core.tool_execution import ToolExecutor, tool_executor
from nexus.core.tools import ToolRegistry, ToolSpec, tool_registry


class ModelProviderExecutionError(RuntimeError):
    """Normalized provider failure used by the fallback controller."""


class OpenAIModelProvider:
    """Provider-neutral adapter around the built-in OpenAI Responses client."""

    name = "openai"

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def generate(
        self,
        *,
        model: ModelSpec,
        input_items: list[Any],
        tools: list[Mapping[str, Any]],
        tool_choice: str,
    ) -> ModelResponse:
        try:
            response = self._get_client().responses.create(
                model=model.model_id,
                input=input_items,
                tools=tools,
                tool_choice=tool_choice,
            )
        except Exception as exc:
            raise ModelProviderExecutionError(f"openai provider failed: {exc}") from exc

        calls: list[Mapping[str, Any]] = []
        for item in response.output:
            if getattr(item, "type", None) == "function_call":
                calls.append(
                    {
                        "name": str(item.name),
                        "arguments": str(item.arguments),
                        "call_id": str(item.call_id),
                    }
                )
        return ModelResponse(
            output=response.output_text,
            response_id=response.id,
            provider=model.provider,
            model_id=model.model_id,
            tool_calls=tuple(calls),
        )


class BYOKModelProvider:
    """Provider-neutral adapter backed by the existing user-owned credential manager."""

    def __init__(self, manager: BYOKProviderManager, user_id: str) -> None:
        if not user_id.strip():
            raise ValueError("user_id is required for BYOK execution")
        self._manager = manager
        self._user_id = user_id

    def generate(
        self,
        *,
        model: ModelSpec,
        input_items: list[Any],
        tools: list[Mapping[str, Any]],
        tool_choice: str,
    ) -> ModelResponse:
        try:
            return self._manager.generate(
                user_id=self._user_id,
                model=model,
                input_items=input_items,
                tools=tools,
                tool_choice=tool_choice,
            )
        except Exception as exc:
            if isinstance(exc, BYOKProviderError):
                raise ModelProviderExecutionError(str(exc)) from exc
            raise ModelProviderExecutionError(f"{model.provider} provider failed: {exc}") from exc


class ModelProviderRegistry:
    """Explicit provider registry used by model execution and tests."""

    def __init__(self, providers: Mapping[str, Any] | None = None) -> None:
        self._providers = dict(providers or {})

    def register(self, provider: Any) -> None:
        name = str(provider.name).strip().lower()
        if not name:
            raise ValueError("provider name cannot be empty")
        self._providers[name] = provider

    def get(self, provider: str) -> Any:
        try:
            return self._providers[provider.strip().lower()]
        except KeyError as exc:
            raise ModelProviderExecutionError(f"no provider registered for '{provider}'") from exc


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    risk_level: str = "low"
    permission: str = "read"
    success: bool = True


@dataclass(frozen=True)
class ExecutionResult:
    model_key: str
    model_id: str
    response_id: str
    output: str
    tool_calls: tuple[ToolCallRecord, ...] = ()
    grounded_evidence: tuple[dict[str, Any], ...] = ()
    fallback_count: int = 0
    fallback_history: tuple[str, ...] = ()


class ToolPermissionPolicy:
    """Compatibility wrapper around NEXUS's centralized permission policy."""

    def __init__(self, policy: PermissionPolicy | None = None) -> None:
        self._policy = policy or PermissionPolicy()

    def authorize(self, task: Task, tool: ToolSpec) -> None:
        decision = self._policy.decide(tool, task.risk_level)
        if decision == PermissionDecision.ALLOW:
            return
        if decision == PermissionDecision.APPROVAL_REQUIRED:
            raise PermissionError(f"Tool '{tool.name}' requires explicit user approval before execution.")
        raise PermissionError(f"Tool '{tool.name}' is blocked by the NEXUS permission policy.")


class ModelExecutor:
    """Executes provider-neutral model calls while preserving the local tool security boundary."""

    def __init__(
        self,
        client: OpenAI | None = None,
        registry: ToolRegistry | None = None,
        policy: ToolPermissionPolicy | None = None,
        max_tool_rounds: int = 8,
        execution_boundary: ToolExecutor | None = None,
        provider_registry: ModelProviderRegistry | None = None,
        byok_manager: BYOKProviderManager | None = None,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be at least 1")
        self._registry = registry or tool_registry
        self._policy = policy or ToolPermissionPolicy()
        self._max_tool_rounds = max_tool_rounds
        self._byok_manager = byok_manager or byok_provider_manager
        if execution_boundary is not None:
            self._execution_boundary = execution_boundary
        elif self._registry is tool_registry:
            self._execution_boundary = tool_executor
        else:
            self._execution_boundary = ToolExecutor(
                registry=self._registry,
                permission_policy=self._policy._policy,
                actor="model-executor",
            )
        self._providers = provider_registry or ModelProviderRegistry()
        if provider_registry is None:
            self._providers.register(OpenAIModelProvider(client=client))

    def _provider(self, model: ModelSpec, *, user_id: str | None, use_byok: bool) -> Any:
        if use_byok:
            return BYOKModelProvider(self._byok_manager, user_id or "")
        return self._providers.get(model.provider)

    @staticmethod
    def _capture_grounded_evidence(
        tool_name: str,
        result: Any,
        target: list[dict[str, Any]],
    ) -> None:
        if tool_name == "search_knowledge" and isinstance(result, dict):
            items = result.get("results", [])
        elif tool_name == "research_knowledge" and isinstance(result, dict):
            items = result.get("sources", [])
        else:
            return
        for evidence in items:
            if not isinstance(evidence, dict):
                continue
            target.append(
                {
                    "citation": evidence.get("citation"),
                    "document_id": evidence.get("document_id"),
                    "chunk_id": evidence.get("chunk_id"),
                    "text": evidence.get("text", ""),
                    "query": evidence.get("query"),
                }
            )

    def execute(
        self,
        task: Task,
        model: ModelSpec,
        allowed_tools: tuple[str, ...] | None = None,
        *,
        user_id: str | None = None,
        use_byok: bool = False,
    ) -> ExecutionResult:
        provider = self._provider(model, user_id=user_id, use_byok=use_byok)
        tools = self._registry.openai_tools() if allowed_tools is None else [
            self._registry.get(name).as_openai_tool() for name in allowed_tools
        ]
        input_items: list[Any] = [{"role": "user", "content": task.objective}]
        if task.context:
            input_items.append({"role": "user", "content": task.context})
        tool_calls: list[ToolCallRecord] = []
        grounded_evidence: list[dict[str, Any]] = []
        tool_rounds = 0
        workspace_token = set_knowledge_workspace(task.workspace_id)
        try:
            while True:
                started_at = time.perf_counter()
                try:
                    response = provider.generate(
                        model=model,
                        input_items=input_items,
                        tools=tools,
                        tool_choice="auto" if tools else "none",
                    )
                except ModelProviderExecutionError as exc:
                    model_health_registry.record_failure(model, str(exc))
                    raise
                except Exception as exc:
                    model_health_registry.record_failure(model, str(exc))
                    raise ModelProviderExecutionError(str(exc)) from exc
                model_health_registry.record_success(
                    model,
                    latency_ms=(time.perf_counter() - started_at) * 1000,
                )

                function_calls = list(response.tool_calls)
                if not function_calls:
                    return ExecutionResult(
                        model_key=model.key,
                        model_id=model.model_id,
                        response_id=response.response_id,
                        output=response.output,
                        tool_calls=tuple(tool_calls),
                        grounded_evidence=tuple(grounded_evidence),
                    )
                if use_byok and model.provider != "openai":
                    input_items.append(
                        {
                            "role": "assistant",
                            "content": response.output or None,
                            "tool_calls": [
                                {
                                    "id": call["call_id"],
                                    "type": "function",
                                    "function": {
                                        "name": call["name"],
                                        "arguments": call["arguments"],
                                    },
                                }
                                for call in function_calls
                            ],
                        }
                    )
                if tool_rounds >= self._max_tool_rounds:
                    raise RuntimeError("NEXUS tool execution limit exceeded")
                tool_rounds += 1
                for call in function_calls:
                    if not (use_byok and model.provider != "openai"):
                        input_items.append(
                            {
                                "type": "function_call",
                                "name": call["name"],
                                "arguments": call["arguments"],
                                "call_id": call["call_id"],
                            }
                        )
                    arguments = json.loads(call["arguments"])
                    tool = self._registry.get(call["name"])
                    self._policy.authorize(task, tool)
                    execution = self._execution_boundary.execute(task, call["name"], arguments)
                    if execution.permission == PermissionDecision.APPROVAL_REQUIRED:
                        raise PermissionError(
                            f"Tool '{call['name']}' requires explicit user approval before execution."
                        )
                    if execution.permission == PermissionDecision.DENY:
                        raise PermissionError(
                            execution.error or f"Tool '{call['name']}' is blocked by the NEXUS permission policy."
                        )
                    result = execution.output
                    success = execution.success
                    if not success:
                        result = {"error": execution.error or "tool execution failed", "tool": call["name"]}
                    tool_calls.append(
                        ToolCallRecord(
                            tool_name=call["name"],
                            arguments=arguments,
                            result=result,
                            risk_level=tool.risk_level,
                            permission=tool.permission,
                            success=success,
                        )
                    )
                    if success:
                        self._capture_grounded_evidence(call["name"], result, grounded_evidence)
                    if use_byok and model.provider != "openai":
                        input_items.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["call_id"],
                                "content": json.dumps(result),
                            }
                        )
                    else:
                        input_items.append(
                            {
                                "type": "function_call_output",
                                "call_id": call["call_id"],
                                "output": json.dumps(result),
                            }
                        )
        finally:
            reset_knowledge_workspace(workspace_token)

    def execute_with_fallback(
        self,
        task: Task,
        plan: FrontierWorkflowPlan,
        allowed_tools: tuple[str, ...] | None = None,
        *,
        user_id: str | None = None,
        use_byok: bool = False,
    ) -> ExecutionResult:
        """Execute a prevalidated primary/fallback cascade on provider failures."""
        history: list[str] = []
        for index, model in enumerate(plan.candidates):
            try:
                result = self.execute(
                    task,
                    model,
                    allowed_tools,
                    user_id=user_id,
                    use_byok=use_byok,
                )
                return ExecutionResult(
                    model_key=result.model_key,
                    model_id=result.model_id,
                    response_id=result.response_id,
                    output=result.output,
                    tool_calls=result.tool_calls,
                    grounded_evidence=result.grounded_evidence,
                    fallback_count=index,
                    fallback_history=tuple(history),
                )
            except ModelProviderExecutionError as exc:
                if index >= len(plan.candidates) - 1:
                    raise
                decision = FrontierFallbackController.decide(
                    plan,
                    current_index=index,
                    reason=FallbackReason.PROVIDER_ERROR,
                )
                if not decision.should_fallback:
                    raise
                history.append(f"{model.key}->{decision.next_model.key}:{exc}")
        raise ModelProviderExecutionError("model fallback plan contained no executable candidates")
