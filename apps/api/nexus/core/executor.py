from dataclasses import dataclass

from openai import OpenAI

from nexus.core.config import settings
from nexus.core.models import ModelSpec
from nexus.core.task import Task


@dataclass(frozen=True)
class ExecutionResult:
    model_key: str
    model_id: str
    response_id: str
    output: str


class ModelExecutor:
    """Executes a routed NEXUS task through the OpenAI Responses API."""

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client or OpenAI(api_key=settings.openai_api_key)

    def execute(self, task: Task, model: ModelSpec) -> ExecutionResult:
        response = self._client.responses.create(
            model=model.model_id,
            input=task.objective,
        )

        return ExecutionResult(
            model_key=model.key,
            model_id=model.model_id,
            response_id=response.id,
            output=response.output_text,
        )
