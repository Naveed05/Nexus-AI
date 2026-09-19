from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.testclient import TestClient

from nexus.core.config import settings
from nexus.core.dataset_workspace import DatasetWorkspace
from nexus.core.documents import DocumentParseError, DocumentWorkspace
from nexus.core.engine import engine
from nexus.core.files import FileNotFoundError as NexusFileNotFoundError
from nexus.core.files import FileRegistry, LocalFileStore
from nexus.core.knowledge import KnowledgeEngine, configure_knowledge_engine
from nexus.core.memory import memory_store
from nexus.core.models import BYOKProviderError, ProviderCredentialError, ProviderNotConfiguredError, ModelSpec, SUPPORTED_PROVIDERS, byok_provider_manager
from nexus.core.research import ResearchEngine
from nexus.core.schemas import ExecutionResponse, ResearchRequest, ResearchResponse, TaskCreate, TaskResponse
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
knowledge_engine = KnowledgeEngine(document_workspace, settings.knowledge_index_path)
configure_knowledge_engine(knowledge_engine)
research_engine = ResearchEngine()


def _workspace_payload(workspace) -> dict:
    return {"workspace_id": str(workspace.workspace_id), "name": workspace.name, "owner_id": workspace.owner_id, "metadata": workspace.metadata, "created_at": workspace.created_at.isoformat()}

def _file_payload(file_ref) -> dict:
    return {"file_id": str(file_ref.file_id), "workspace_id": str(file_ref.workspace_id) if file_ref.workspace_id else None, "filename": file_ref.filename, "mime_type": file_ref.mime_type, "size_bytes": file_ref.size_bytes, "metadata": file_ref.metadata, "created_at": file_ref.created_at.isoformat()}

def _memory_payload(record) -> dict:
    return {"memory_id": str(record.memory_id), "workspace_id": str(record.workspace_id) if record.workspace_id else None, "content": record.content, "tags": list(record.tags), "importance": record.importance, "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat()}

def _require_workspace(workspace_id: UUID):
    try: return workspace_registry.get(workspace_id)
    except WorkspaceNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc

def _workspace_context_text(workspace_id: UUID | None) -> str | None:
    return workspace_registry.context(workspace_id).as_text() if workspace_id is not None else None

def _build_task(payload: TaskCreate) -> Task:
    if payload.workspace_id is not None: _require_workspace(payload.workspace_id)
    context_parts = [part for part in (payload.context, _workspace_context_text(payload.workspace_id)) if part]
    return Task(**payload.model_dump(exclude={"context"}), context="\n".join(context_parts) or None)

@app.get("/api/v1/health")
def health() -> dict[str, str]: return {"status": "ok", "service": "nexus-api"}

@app.get("/api/v1/byok/providers")
def list_byok_providers() -> dict:
    """List supported BYOK providers without exposing credentials."""
    return {"providers": sorted(SUPPORTED_PROVIDERS)}


def _byok_user(user_id: str | None) -> str:
    value = (user_id or "").strip()
    if not value:
        raise HTTPException(status_code=401, detail="X-Nexus-User-ID header is required")
    return value


@app.get("/api/v1/byok/credentials")
def list_byok_credentials(x_nexus_user_id: str | None = Header(default=None)) -> dict:
    user_id = _byok_user(x_nexus_user_id)
    return {
        "providers": [
            {"provider": provider, "configured": provider in byok_provider_manager.configured(user_id)}
            for provider in sorted(SUPPORTED_PROVIDERS)
        ]
    }


@app.put("/api/v1/byok/credentials/{provider}")
def configure_byok_credential(
    provider: str,
    payload: dict,
    x_nexus_user_id: str | None = Header(default=None),
) -> dict:
    user_id = _byok_user(x_nexus_user_id)
    api_key = payload.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise HTTPException(status_code=422, detail="api_key is required")
    if len(api_key.strip()) < 8:
        raise HTTPException(status_code=422, detail="api_key is too short")
    try:
        masked = byok_provider_manager.configure(user_id, provider, api_key)
    except ProviderCredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"provider": provider.strip().lower(), "configured": True, "masked_key": masked}


@app.delete("/api/v1/byok/credentials/{provider}", status_code=204)
def remove_byok_credential(
    provider: str,
    x_nexus_user_id: str | None = Header(default=None),
) -> Response:
    user_id = _byok_user(x_nexus_user_id)
    try:
        byok_provider_manager.credential(user_id, provider)
    except ProviderNotConfiguredError:
        return Response(status_code=204)
    except ProviderCredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    byok_provider_manager.remove(user_id, provider)
    return Response(status_code=204)


@app.post("/api/v1/byok/generate")
def generate_with_byok(
    payload: dict,
    x_nexus_user_id: str | None = Header(default=None),
) -> dict:
    user_id = _byok_user(x_nexus_user_id)
    provider = str(payload.get("provider", "")).strip().lower()
    model_id = str(payload.get("model", "")).strip()
    prompt = str(payload.get("prompt", "")).strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unsupported provider: {provider}")
    if not model_id:
        raise HTTPException(status_code=422, detail="model is required")
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt is required")
    if len(prompt) > 20_000:
        raise HTTPException(status_code=422, detail="prompt is too long")
    try:
        model = ModelSpec(
            key=f"byok:{provider}:{model_id}",
            model_id=model_id,
            provider=provider,
            tier="byok",
            description="User-supplied BYOK model",
            capabilities=frozenset({"reasoning", "coding", "research", "tools"}),
            reasoning_levels=frozenset({"low", "medium", "high"}),
            context_window=128_000,
            supports_tools=False,
            cost_score=0,
            latency_score=0,
        )
        response = byok_provider_manager.generate(
            user_id=user_id,
            model=model,
            input_items=[{"role": "user", "content": prompt}],
            tools=[],
            timeout_seconds=30,
        )
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ProviderCredentialError, BYOKProviderError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "provider": response.provider,
        "model": response.model_id,
        "response_id": response.response_id,
        "output": response.output,
    }



@app.post("/api/v1/memories", status_code=201)
def create_memory(payload: dict) -> dict:
    workspace_id = payload.get("workspace_id")
    try: parsed_workspace = UUID(str(workspace_id)) if workspace_id else None
    except ValueError as exc: raise HTTPException(status_code=422, detail="workspace_id must be a UUID") from exc
    if parsed_workspace is not None: _require_workspace(parsed_workspace)
    tags = payload.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise HTTPException(status_code=422, detail="tags must be an array of strings")
    try:
        record = memory_store.remember(str(payload.get("content", "")), workspace_id=parsed_workspace, tags=tuple(tags), importance=float(payload.get("importance", 0.5)))
    except (TypeError, ValueError) as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _memory_payload(record)

@app.get("/api/v1/workspaces/{workspace_id}/memories")
def list_memories(workspace_id: UUID) -> list[dict]:
    _require_workspace(workspace_id)
    return [_memory_payload(record) for record in memory_store.list(workspace_id=workspace_id)]

@app.post("/api/v1/workspaces/{workspace_id}/memories/recall")
def recall_memories(workspace_id: UUID, payload: dict) -> dict:
    _require_workspace(workspace_id)
    query = str(payload.get("query", "")).strip()
    try: top_k = max(1, min(int(payload.get("top_k", 5)), 20))
    except (TypeError, ValueError) as exc: raise HTTPException(status_code=422, detail="top_k must be an integer") from exc
    try: matches = memory_store.recall_ranked(query, workspace_id=workspace_id, top_k=top_k)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"query": query, "workspace_id": str(workspace_id), "matches": [{**_memory_payload(match.record), "relevance": match.relevance, "confidence": match.confidence} for match in matches]}

@app.delete("/api/v1/workspaces/{workspace_id}/memories/{memory_id}", status_code=204)
def delete_memory(workspace_id: UUID, memory_id: UUID) -> Response:
    _require_workspace(workspace_id)
    try: memory_store.forget(memory_id, workspace_id=workspace_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)

@app.post("/api/v1/tasks", response_model=TaskResponse, status_code=201)
def create_task(payload: TaskCreate) -> TaskResponse:
    task = _build_task(payload); route = engine.route_task(task)
    return TaskResponse(task_id=str(task.task_id), objective=task.objective, status=task.status, risk_level=task.risk_level, created_at=task.created_at.isoformat(), capabilities=task.capabilities, selected_model=route.model.model_id, workspace_id=str(task.workspace_id) if task.workspace_id else None)

@app.post("/api/v1/tasks/execute", response_model=ExecutionResponse, status_code=200)
def execute_task(payload: TaskCreate) -> ExecutionResponse:
    task = _build_task(payload); result = engine.run(task)
    verification = result.verification
    return ExecutionResponse(
        task_id=str(task.task_id), model=result.model.model_id, response_id=result.execution.response_id, output=result.execution.output,
        verification_passed=result.state.verification_passed, verification_checks=verification.checks, verification_issues=list(verification.issues),
        grounding_score=verification.grounding_score,
        grounding=[{"citation": item.citation, "claim": item.claim, "overlap_score": item.overlap_score, "supported": item.supported} for item in verification.grounding],
        tool_calls=len(result.execution.tool_calls), events=[event.event_type.value for event in result.events],
    )

@app.post("/api/v1/research", response_model=ResearchResponse, status_code=200)
def research(payload: ResearchRequest) -> ResearchResponse:
    _require_workspace(payload.workspace_id)
    try:
        result = research_engine.research(payload.question, workspace_id=payload.workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    body = result.as_dict()
    synthesis = body["synthesis"]
    return ResearchResponse(
        question=body["question"], workspace_id=str(payload.workspace_id), queries=body["queries"],
        evidence_count=body["evidence_count"], source_count=synthesis["source_count"],
        document_count=synthesis["document_count"], sources=body["sources"], synthesis=synthesis,
    )

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
        file_ref = file_store.put(await file.read(), filename=filename, workspace_id=workspace_id, mime_type=file.content_type); file_registry.register(file_ref); workspace_registry.context(workspace_id).add_file(file_ref.file_id)
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
    file_store.delete(file_ref); file_registry.remove(file_id, workspace_id=workspace_id); workspace_registry.context(workspace_id).remove_file(file_id); return Response(status_code=204)

@app.post("/api/v1/workspaces/{workspace_id}/documents", status_code=201)
async def upload_workspace_document(workspace_id: UUID, file: UploadFile = File(...)) -> dict:
    _require_workspace(workspace_id); filename = Path(file.filename or "").name
    if not filename: raise HTTPException(status_code=422, detail="filename cannot be empty")
    try:
        document, chunk_count = knowledge_engine.ingest(await file.read(), filename=filename, workspace_id=workspace_id, metadata={"content_type": file.content_type or "application/octet-stream"}); workspace_registry.context(workspace_id).add_document(document.document_id)
    except DocumentParseError as exc: raise HTTPException(status_code=415, detail=str(exc)) from exc
    return {"document_id": str(document.document_id), "workspace_id": str(workspace_id), "filename": document.filename, "file_format": document.file_format, "size_bytes": document.size_bytes, "artifact_id": str(document.artifact_id) if document.artifact_id else None, "chunk_count": chunk_count, "metadata": document.metadata}

@app.get("/api/v1/workspaces/{workspace_id}/documents")
def list_workspace_documents(workspace_id: UUID) -> list[dict]:
    _require_workspace(workspace_id); return [{"document_id": str(document_id)} for document_id in workspace_registry.context(workspace_id).document_ids]

@app.post("/api/v1/workspaces/{workspace_id}/search")
def search_workspace(workspace_id: UUID, payload: dict) -> dict:
    _require_workspace(workspace_id); query = str(payload.get("query", "")).strip()
    try: top_k = max(1, min(int(payload.get("top_k", 5)), 20))
    except (TypeError, ValueError) as exc: raise HTTPException(status_code=422, detail="top_k must be an integer") from exc
    document_id = payload.get("document_id")
    try: parsed_document_id = UUID(str(document_id)) if document_id else None
    except ValueError as exc: raise HTTPException(status_code=422, detail="document_id must be a UUID") from exc
    if parsed_document_id is not None and parsed_document_id not in workspace_registry.context(workspace_id).document_ids: raise HTTPException(status_code=404, detail="Document does not belong to the requested workspace")
    return knowledge_engine.search(query, workspace_id=workspace_id, top_k=top_k, document_id=parsed_document_id).as_dict()
