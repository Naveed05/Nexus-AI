from fastapi import FastAPI

from nexus.core.config import settings
from nexus.core.schemas import TaskCreate, TaskResponse
from nexus.core.task import Task

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nexus-api"}


@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=201)
def create_task(payload: TaskCreate) -> TaskResponse:
    task = Task(**payload.model_dump())
    return TaskResponse(
        task_id=str(task.task_id),
        objective=task.objective,
        status=task.status,
        risk_level=task.risk_level,
        created_at=task.created_at.isoformat(),
        capabilities=task.capabilities,
    )
