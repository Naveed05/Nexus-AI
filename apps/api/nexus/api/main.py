from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.testclient import TestClient

from nexus.core.config import settings
from nexus.core.dataset_workspace import DatasetWorkspace
from nexus.core.documents import DocumentParseError, DocumentWorkspace
from nexus.core.engine import engine
from nexus.core.files import FileNotFoundError as NexusFileNotFoundError
from nexus.core.files import FileRegistry, LocalFileStore
from nexus.core.retrieval import JsonVectorStore, RetrievalEngine
from nexus.core.schemas import ExecutionResponse, TaskCreate, TaskResponse
from nexus.core.task import Task
from nexus.core.tools import configure_dataset_workspace
from nexus.core.workspaces import WorkspaceNotFoundError, workspace_registry

app = FastAPI(title=settings.app_name, version="0.1.0")
client = TestClient(app)
dataset_workspace = DatasetWorkspace(settings.dataset_storage_path)
configure_dataset_workspace(dataset_workspace)
file_store = LocalFileStore(settings.file_storage_path)
file_registry = FileRegistry()
document_workspace = DocumentWorkspace(Path(settings.file_storage_path) / "documents")
retrieval_engine = RetrievalEngine(document_workspace, store=JsonVectorStore(settings.knowledge_index_path))


def _workspace_payload(workspace) -> dict:
    return {"workspace_id": str(workspace.workspace_id), "name": workspace.name, "owner_id": workspace.owner_id, "metadata": workspace.metadata, "created_at": workspace.created_at.isoformat()}

def _file_payload(file_ref) -> dict:
    return {"file_id": str(file_ref.file_id), "workspace_id": str(file_ref.workspace_id) if file_ref.workspace_id else None, "filename": file_ref.filename, "mime_type": file_ref.mime_type, "size_bytes": file_ref.size_bytes, "metadata": file_ref.metadata, "created_at": file_ref.created_at.isoformat()}

def _require_workspace(workspace_id: UUID):
    try:
        return workspace_registry.get(workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

def _workspace_context_text(workspace_id: UUID | None) -> str | None:
    return workspace_registry.context(workspace_id).as_text() if workspace_id is not None else None

def _build_task(payload: TaskCreate) -> Task:
    if payload.workspace_id is not None:
        _require_workspace(payload.workspace_id)
    context_parts = [part for part in (payload.context, _workspace_context_text(payload.workspace_id)) if part]
    return Task(**payload.model_dump(exclude={"context"}), context="\n".join(context_parts) or None)

@app.get("/api/v1/health")
def health() -> dict[str, str]: return {"status": "ok", "service": "nexus-api"}

@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=201)
def create_task(payload: TaskCreate) -> TaskResponse:
    task = _build_task(payload); route = engine.route_task(task)
    return TaskResponse(task_id=str(task.task_id), objective=task.objective, status=task.status, risk_level=task.risk_level, created_at=task.created_at.isoformat(), capabilities=task.capabilities, selected_model=route.model.model_id, workspace_id=str(task.workspace_id) if task.workspace_id else None)

@app.post("/api/v1/tasks/execute", response_model=ExecutionResponse, status_code=200)
def execute_task(payload: TaskCreate) -> ExecutionResponse:
    task = _build_task(payload); result = engine.run(task)
    return ExecutionResponse(task_id=str(task.task_id), model=result.model.model_id, response_id=result.execution.response_id, output=result.execution.output, verification_passed=result.state.verification_passed, tool_calls=len(result.execution.tool_calls), events=[event.event_type.value for event in result.events])

@app.post("/api/v1/datasets", status_code=201)
async def upload_dataset(file: UploadFile = File(...)) -> dict:
    filename = Path(file.filename or "").name; suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in {"csv", "parquet", "json"}: raise HTTPException(status_code=415, detail="Supported dataset formats: csv, parquet, json")
    try: dataset = dataset_workspace.register(await file.read(), filename=filename, file_format=suffix, metadata={"content_type": file.content_type or "application/octet-stream"})
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"dataset_id": str(dataset.dataset_id), "filename": dataset.filename, "file_format": dataset.file_format, "size_bytes": dataset.size_bytes, "artifact_id": str(dataset.artifact_id) if dataset.artifact_id else None, "metadata": dataset.metadata}

@app.post("/api/v1/workspaces", status_code=201)
def create_workspace(payload: dict) -> dict:
    name = str(payload.get("name", "Workspace")); owner_id = payload.get("owner_id"); metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, dict): raise HTTPException(status_code=422, detail="metadata must be an object")
    try: workspace = workspace_registry.create(name=name, owner_id=owner_id, metadata=metadata)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _workspace_payload(workspace)

@app.get("/api/v1/workspaces")
def list_workspaces() -> list[dict]: return [_workspace_payload(workspace) for workspace in workspace_registry.list()]

@app.get("/api/v1/workspaces/{workspace_id}")
def get_workspace(workspace_id: UUID) -> dict: return _workspace_payload(_require_workspace(workspace_id))

@app.post("/api/v1/workspaces/{workspace_id}/files", status_code=201)
async def upload_workspace_file(workspace_id: UUID, file: UploadFile = File(...)) -> dict:
    _require_workspace(workspace_id); filename = Path(file.filename or "").name
    if not filename: raise HTTPException(status_code=422, detail="filename cannot be empty")
    try:
        file_ref = file_store.put(await file.read(), filename=filename, workspace_id=workspace_id, mime_type=file.content_type)
        file_registry.register(file_ref); workspace_registry.context(workspace_id).add_file(file_ref.file_id)
    except (TypeError, ValueError) as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _file_payload(file_ref)

@app.get("/api/v1/workspaces/{workspace_id}/files")
def list_workspace_files(workspace_id: UUID) -> list[dict]:
    _require_workspace(workspace_id); return [_file_payload(f) for f in file_registry.list(workspace_id=workspace_id)]

@app.get("/api/v1/workspaces/{workspace_id}/files/{file_id}")
def download_workspace_file(workspace_id: UUID, file_id: UUID) -> Response:
    _require_workspace(workspace_id)
    try: file_ref = file_registry.get(file_id, workspace_id=workspace_id); data = file_store.get(file_ref)
    except NexusFileNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=data, media_type=file_ref.mime_type or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{file_ref.filename}"'})

@app.delete("/api/v1/workspaces/{workspace_id}/files/{file_id}", status_code=204)
def delete_workspace_file(workspace_id: UUID, file_id: UUID) -> Response:
    _require_workspace(workspace_id)
    try: file_ref = file_registry.get(file_id, workspace_id=workspace_id)
    except NexusFileNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    file_store.delete(file_ref); file_registry.remove(file_id, workspace_id=workspace_id); workspace_registry.context(workspace_id).remove_file(file_id)
    return Response(status_code=204)

@app.post("/api/v1/workspaces/{workspace_id}/documents", status_code=201)
async def upload_workspace_document(workspace_id: UUID, file: UploadFile = File(...)) -> dict:
    _require_workspace(workspace_id); filename = Path(file.filename or "").name
    if not filename: raise HTTPException(status_code=422, detail="filename cannot be empty")
    try:
        document = document_workspace.register(await file.read(), filename=filename, workspace_id=workspace_id, metadata={"content_type": file.content_type or "application/octet-stream"})
        retrieval_engine.index_document(document.document_id); workspace_registry.context(workspace_id).add_document(document.document_id)
    except DocumentParseError as exc: raise HTTPException(status_code=415, detail=str(exc)) from exc
    return {"document_id": str(document.document_id), "workspace_id": str(workspace_id), "filename": document.filename, "file_format": document.file_format, "size_bytes": document.size_bytes, "artifact_id": str(document.artifact_id) if document.artifact_id else None, "chunk_count": len(document_workspace.get_chunks(document.document_id)), "metadata": document.metadata}

@app.get("/api/v1/workspaces/{workspace_id}/documents")
def list_workspace_documents(workspace_id: UUID) -> list[dict]:
    context = workspace_registry.context(workspace_id); return [{"document_id": str(document_id)} for document_id in context.document_ids]

@app.post("/api/v1/workspaces/{workspace_id}/search")
def search_workspace(workspace_id: UUID, payload: dict) -> list[dict]:
    _require_workspace(workspace_id); query = str(payload.get("query", "")).strip(); top_k = int(payload.get("top_k", 5))
    results = retrieval_engine.search(query, workspace_id=workspace_id, top_k=top_k)
    return [{"chunk_id": str(r.chunk.chunk_id), "document_id": str(r.chunk.document_id), "score": r.score, "vector_score": r.vector_score, "lexical_score": r.lexical_score, "citation": r.citation, "text": r.chunk.text, "metadata": r.chunk.metadata} for r in results]
