from fastapi import FastAPI

from nexus.core.config import settings
from nexus.core.schemas import TaskCreate, TaskResponse

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nexus-api"}


@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=201)
def create_task(payload: TaskCreate) -> TaskResponse:
    return TaskResponse(
        task_id="task-local-001",
        objective=payload.objective,
        status="accepted",
    )
