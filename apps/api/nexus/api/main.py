from fastapi import FastAPI

from nexus.core.config import settings
from nexus.core.engine import engine
from nexus.core.events import EventType
from nexus.core.schemas import ExecutionResponse, TaskCreate, TaskResponse
from nexus.core.task import Task

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nexus-api"}


@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=201)
def create_task(payload: TaskCreate) -> TaskResponse:
    task = Task(**payload.model_dump())
    route = engine.route_task(task)
    return TaskResponse(
        task_id=str(task.task_id),
        objective=task.objective,
        status=task.status,
        risk_level=task.risk_level,
        created_at=task.created_at.isoformat(),
        capabilities=task.capabilities,
        selected_model=route.model.model_id,
    )


@app.post("/api/v1/tasks/execute", response_model=ExecutionResponse, status_code=200)
def execute_task(payload: TaskCreate) -> ExecutionResponse:
    task = Task(**payload.model_dump())
    result = engine.run(task)
    return ExecutionResponse(
        task_id=str(task.task_id),
        model=result.model.model_id,
        response_id=result.execution.response_id,
        output=result.execution.output,
        verification_passed=result.state.verification_passed,
        tool_calls=len(result.execution.tool_calls),
        events=[event.event_type.value for event in result.events],
    )
