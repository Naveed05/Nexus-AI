from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from nexus.core.config import settings
from nexus.core.dataset_workspace import DatasetWorkspace
from nexus.core.engine import engine
from nexus.core.schemas import ExecutionResponse, TaskCreate, TaskResponse
from nexus.core.task import Task
from nexus.core.tools import configure_dataset_workspace

app = FastAPI(title=settings.app_name, version="0.1.0")
dataset_workspace = DatasetWorkspace(settings.dataset_storage_path)
configure_dataset_workspace(dataset_workspace)


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


@app.post("/api/v1/datasets", status_code=201)
async def upload_dataset(file: UploadFile = File(...)) -> dict:
    """Store a supported dataset and return its stable dataset reference."""
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in {"csv", "parquet", "json"}:
        raise HTTPException(status_code=415, detail="Supported dataset formats: csv, parquet, json")

    data = await file.read()
    try:
        dataset = dataset_workspace.register(
            data,
            filename=filename,
            file_format=suffix,
            metadata={"content_type": file.content_type or "application/octet-stream"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "dataset_id": str(dataset.dataset_id),
        "filename": dataset.filename,
        "file_format": dataset.file_format,
        "size_bytes": dataset.size_bytes,
        "artifact_id": str(dataset.artifact_id) if dataset.artifact_id else None,
        "metadata": dataset.metadata,
    }
