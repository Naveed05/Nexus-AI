from dataclasses import dataclass

from nexus.core.models import ModelSpec
from nexus.core.router import router
from nexus.core.task import Task


@dataclass(frozen=True)
class TaskRoute:
    task_id: str
    model: ModelSpec


class NexusEngine:
    """Kernel entry point that converts a task into an execution route."""

    def route_task(self, task: Task) -> TaskRoute:
        selected_model = router.route(task)
        return TaskRoute(task_id=str(task.task_id), model=selected_model)


engine = NexusEngine()
