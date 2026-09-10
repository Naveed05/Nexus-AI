from dataclasses import dataclass

from nexus.core.executor import ExecutionResult, ModelExecutor
from nexus.core.models import ModelSpec
from nexus.core.router import TaskRouter
from nexus.core.task import Task


@dataclass(frozen=True)
class EngineResult:
    task: Task
    model: ModelSpec
    execution: ExecutionResult


class NexusEngine:
    """Coordinates task routing and model execution."""

    def __init__(
        self,
        router: TaskRouter | None = None,
        executor: ModelExecutor | None = None,
    ) -> None:
        self._router = router or TaskRouter()
        self._executor = executor or ModelExecutor()

    def run(self, task: Task) -> EngineResult:
        model = self._router.route(task)
        execution = self._executor.execute(task, model)
        return EngineResult(task=task, model=model, execution=execution)


engine = NexusEngine()
