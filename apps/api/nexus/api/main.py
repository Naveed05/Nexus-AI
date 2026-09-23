from pathlib import Path
from uuid import UUID
import json
import time

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles

from nexus.core.config import settings
from nexus.core.dataset_workspace import DatasetWorkspace
from nexus.core.documents import DocumentParseError, DocumentWorkspace
from nexus.core.engine import engine
from nexus.core.files import FileNotFoundError as NexusFileNotFoundError
from nexus.core.files import FileRegistry, LocalFileStore
from nexus.core.knowledge import KnowledgeEngine, configure_knowledge_engine
from nexus.core.memory import MemoryKind, memory_store
from nexus.core.models import BYOKProviderError, ProviderCredentialError, ProviderNotConfiguredError, ModelSpec, SUPPORTED_PROVIDERS, byok_provider_manager, model_health_registry, model_registry
from nexus.core.research import ResearchEngine
from nexus.core.runtime import AgentRuntime, RunBudget
from nexus.core.production_runtime import ProductionRuntime
from nexus.core.product import product_catalog
from nexus.core.http_telemetry import observe_http_request
from nexus.core.observability import observability
from nexus.core.metrics import service_metrics
from nexus.core.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter
from nexus.core.scale import build_scale_topology, topology_payload
from nexus.core.production_scale import build_scale_deployment, deployment_payload
from nexus.core.workflow_templates import get_workflow_template, list_workflow_templates
from nexus.core.multi_agent import DelegationRequest, default_agent_registry
from nexus.core.supervisor import AgentSupervisor
from nexus.core.collaboration_audit import CollaborationAuditLog
from nexus.core.control_center import build_control_center_summary
from nexus.core.artifacts import ArtifactNotFoundError, ArtifactRegistry, LocalArtifactStore
from nexus.core.schemas import ExecutionResponse, ResearchRequest, ResearchResponse, TaskCreate, TaskResponse
from nexus.core.task import Task
from nexus.core.tool_execution import tool_executor
from nexus.core.tools import configure_dataset_workspace, tool_registry
from nexus.core.workspaces import WorkspaceNotFoundError, workspace_registry

app = FastAPI(title=settings.app_name, version=settings.service_version)
artifact_store = LocalArtifactStore(settings.artifact_storage_path)
artifact_registry = ArtifactRegistry(settings.artifact_registry_path)
app.middleware("http")(observe_http_request)

@app.middleware("http")
async def beta_guard(request: Request, call_next):
    if request.method != "OPTIONS":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_body_bytes:
            return Response("request body too large", status_code=413)
        client_id = request.headers.get("X-Nexus-User-ID") or (request.client.host if request.client else "unknown")
        try:
            rate_limiter.check(client_id)
        except RateLimitExceeded:
            return Response("rate limit exceeded", status_code=429, headers={"Retry-After": "60"})
        if settings.environment.lower() == "production" and settings.beta_access_key:
            if request.headers.get("X-Nexus-Beta-Key") != settings.beta_access_key:
                return Response("beta access key required", status_code=401)
    return await call_next(request)

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    )
    return response
@app.get("/api/v1/product/templates")
def product_templates() -> list[dict]:
    return [
        {"template_id": item.template_id, "name": item.name, "description": item.description,
         "objective": item.objective, "capabilities": list(item.capabilities), "risk_level": item.risk_level}
        for item in list_workflow_templates()
    ]


@app.get("/api/v1/product/templates/{template_id}")
def product_template(template_id: str) -> dict:
    try:
        item = get_workflow_template(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown workflow template") from exc
    return {"template_id": item.template_id, "name": item.name, "description": item.description,
            "objective": item.objective, "capabilities": list(item.capabilities), "risk_level": item.risk_level}


@app.get("/api/v1/product/onboarding")
def product_onboarding(x_user_id: str = Header(default="local-user")) -> dict:
    user_id = x_user_id.strip() or "local-user"
    profile = product_catalog.profile(user_id)
    return {"steps": [{"id": "workspace", "label": "Create or select a workspace", "complete": bool(workspace_registry.list())}, {"id": "template", "label": "Start from a workflow template", "complete": True}, {"id": "execution", "label": "Run and verify a task", "complete": False}, {"id": "memory", "label": "Save useful workspace context", "complete": False}], "plan_id": profile.plan_id}


@app.get("/api/v1/product/plans")
def product_plans() -> list[dict]:
    return [
        {"plan_id": plan.plan_id, "name": plan.name, "description": plan.description,
         "monthly_run_limit": plan.monthly_run_limit, "monthly_file_limit": plan.monthly_file_limit,
         "max_file_bytes": plan.max_file_bytes, "features": list(plan.features)}
        for plan in product_catalog.plans()
    ]


@app.get("/api/v1/product/profile")
def product_profile(x_user_id: str = Header(default="local-user")) -> dict:
    profile = product_catalog.profile(x_user_id.strip() or "local-user")
    return {"user_id": profile.user_id, "plan_id": profile.plan_id, "created_at": profile.created_at.isoformat()}


@app.get("/api/v1/product/usage")
def product_usage(x_user_id: str = Header(default="local-user")) -> dict:
    usage = product_catalog.usage(x_user_id.strip() or "local-user")
    return {"user_id": usage.user_id, "plan_id": usage.plan_id, "runs_used": usage.runs_used,
            "runs_limit": usage.runs_limit, "files_used": usage.files_used,
            "files_limit": usage.files_limit, "reset_at": usage.reset_at.isoformat()}


WEB_ROOT = Path(__file__).resolve().parents[3] / "web"
app.mount("/web", StaticFiles(directory=WEB_ROOT), name="web")

@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")
client = TestClient(app)
dataset_workspace = DatasetWorkspace(settings.dataset_storage_path)
configure_dataset_workspace(dataset_workspace)
file_store = LocalFileStore(settings.file_storage_path)
file_registry = FileRegistry()
document_workspace = DocumentWorkspace(Path(settings.file_storage_path) / "documents")
knowledge_engine = KnowledgeEngine(document_workspace, settings.knowledge_index_path)
configure_knowledge_engine(knowledge_engine)
research_engine = ResearchEngine()
agent_runtime = AgentRuntime(settings.run_storage_path,)
production_runtime = ProductionRuntime(store_path=settings.run_storage_path, engine=engine)
rate_limiter = SlidingWindowRateLimiter(limit=settings.rate_limit_per_minute)
collaboration_audit = CollaborationAuditLog(settings.collaboration_audit_storage_path)


def _workspace_payload(workspace) -> dict:
    return {"workspace_id": str(workspace.workspace_id), "name": workspace.name, "owner_id": workspace.owner_id, "metadata": workspace.metadata, "created_at": workspace.created_at.isoformat()}

def _file_payload(file_ref) -> dict:
    return {"file_id": str(file_ref.file_id), "workspace_id": str(file_ref.workspace_id) if file_ref.workspace_id else None, "filename": file_ref.filename, "mime_type": file_ref.mime_type, "size_bytes": file_ref.size_bytes, "metadata": file_ref.metadata, "created_at": file_ref.created_at.isoformat()}

def _memory_payload(record) -> dict:
    return {
        "memory_id": str(record.memory_id),
        "workspace_id": str(record.workspace_id) if record.workspace_id else None,
        "content": record.content,
        "tags": list(record.tags),
        "importance": record.importance,
        "memory_kind": record.memory_kind.value,
        "source": record.source,
        "source_id": record.source_id,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "supersedes_id": str(record.supersedes_id) if record.supersedes_id else None,
        "archived": record.archived,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }

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
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nexus-api", "version": settings.service_version}


@app.get("/api/v1/scale/topology")
def scale_topology() -> dict:
    topology = build_scale_topology(
        state_backend=settings.state_backend,
        queue_backend=settings.queue_backend,
        cache_backend=settings.cache_backend,
        object_storage_backend=settings.object_storage_backend,
    )
    return topology_payload(topology)


def _scale_deployment():
    topology = build_scale_topology(
        state_backend=settings.state_backend,
        queue_backend=settings.queue_backend,
        cache_backend=settings.cache_backend,
        object_storage_backend=settings.object_storage_backend,
    )
    return build_scale_deployment(
        mode=settings.deployment_mode,
        region=settings.deployment_region,
        instance_id=settings.instance_id,
        topology=topology,
    )


@app.get("/api/v1/scale/deployment")
def scale_deployment() -> dict:
    return deployment_payload(_scale_deployment())


@app.get("/api/v1/ready")
def readiness() -> dict:
    runtime = production_runtime.health()
    deployment = _scale_deployment()
    checks = {
        "runtime": runtime.get("status") == "ready",
        "frontend": WEB_ROOT.exists(),
        "scale_contract": deployment.ready,
    }
    return {
        "status": "ready" if all(checks.values()) else "not_ready",
        "service": "nexus-api",
        "checks": checks,
        "scale": deployment_payload(deployment),
    }


@app.get("/api/v1/observability/summary")
def observability_summary() -> dict:
    return {"service": settings.app_name, "version": settings.service_version, **observability.health()}


@app.get("/api/v1/metrics", response_class=Response)
def metrics() -> Response:
    return Response(service_metrics.prometheus(settings.app_name), media_type="text/plain; version=0.0.4")



@app.get("/api/v1/control-center/summary")
def control_center_summary() -> dict:
    deployment = deployment_payload(_scale_deployment())
    runtime = production_runtime.health()
    agents = list_agents()
    audit_stats = collaboration_audit.stats()
    audit_valid, audit_error = collaboration_audit.verify()
    audit = {**audit_stats, "valid": audit_valid, "error": audit_error}
    models = list_models()
    tools = []
    for contract in tool_registry.contracts():
        snapshot = tool_executor.health(contract["name"])
        tools.append({
            **contract,
            "health": {
                "healthy": snapshot.healthy,
                "executions": snapshot.executions,
                "successes": snapshot.successes,
                "failures": snapshot.failures,
                "consecutive_failures": snapshot.consecutive_failures,
                "last_error": snapshot.last_error,
                "last_success_at": snapshot.last_success_at.isoformat() if snapshot.last_success_at else None,
                "disabled_until": snapshot.disabled_until.isoformat() if snapshot.disabled_until else None,
            },
        })
    runs = list_agent_runs()
    return build_control_center_summary(
        deployment=deployment,
        runtime=runtime,
        agents=agents,
        audit=audit,
        models=models,
        tools=tools,
        runs=runs,
    )


@app.get("/api/v1/agents")
def list_agents() -> list[dict]:
    return [{"agent_id": a.agent_id, "role": a.role.value, "capabilities": list(a.capabilities), "max_steps": a.max_steps} for a in default_agent_registry().list()]


@app.post("/api/v1/agents/collaborate")
def build_collaboration(payload: dict) -> dict:
    objective = str(payload.get("objective", "")).strip()
    requests = tuple(DelegationRequest(str(item.get("objective", "")).strip(), str(item.get("required_capability", "")).strip(), str(item.get("requester", "supervisor")).strip()) for item in payload.get("requests", []))
    try:
        result = AgentSupervisor().build_plan(objective, requests)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    collaboration_audit.append("plan_created", "supervisor", {"objective": result.plan.objective, "workstream_count": len(result.plan.workstreams), "approval_required": result.approval_required})
    return {"objective": result.plan.objective, "workstreams": [{"workstream_id": str(w.workstream_id), "objective": w.objective, "agent_id": w.agent_id, "dependencies": [str(d) for d in w.dependencies], "status": w.status} for w in result.plan.workstreams], "approval_required": result.approval_required, "rationale": list(result.rationale)}


@app.get("/api/v1/agents/audit")
def collaboration_audit_events(
    limit: int = 100,
    event_type: str | None = None,
    actor: str | None = None,
    before_sequence: int | None = None,
) -> list[dict]:
    try:
        events = collaboration_audit.list(
            limit=limit,
            event_type=event_type,
            actor=actor,
            before_sequence=before_sequence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [
        {
            "sequence": event.sequence,
            "event_type": event.event_type,
            "actor": event.actor,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
            "previous_hash": event.previous_hash,
            "event_hash": event.event_hash,
        }
        for event in events
    ]


@app.get("/api/v1/agents/audit/summary")
def collaboration_audit_summary() -> dict:
    stats = collaboration_audit.stats()
    valid, error = collaboration_audit.verify()
    return {**stats, "valid": valid, "error": error}


@app.get("/api/v1/agents/audit/verify")
def verify_collaboration_audit() -> dict:
    valid, error = collaboration_audit.verify()
    return {"valid": valid, "error": error, "event_count": len(collaboration_audit.list(limit=2048))}


@app.get("/api/v1/tools")
def list_tools() -> list[dict]:
    """Expose provider-neutral tool contracts for capability discovery."""
    return list(tool_registry.contracts())


@app.get("/api/v1/tools/capabilities")
def list_tool_capabilities() -> dict:
    return {"capabilities": list(tool_registry.capabilities())}


@app.get("/api/v1/tools/{tool_name}")
def get_tool_contract(tool_name: str) -> dict:
    try:
        return tool_registry.get(tool_name).contract()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/tools/{tool_name}/health")
def get_tool_health(tool_name: str) -> dict:
    try:
        tool_registry.get(tool_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snapshot = tool_executor.health(tool_name)
    return {
        "tool_name": snapshot.tool_name,
        "healthy": snapshot.healthy,
        "executions": snapshot.executions,
        "successes": snapshot.successes,
        "failures": snapshot.failures,
        "consecutive_failures": snapshot.consecutive_failures,
        "last_error": snapshot.last_error,
        "last_success_at": snapshot.last_success_at.isoformat() if snapshot.last_success_at else None,
        "disabled_until": snapshot.disabled_until.isoformat() if snapshot.disabled_until else None,
    }

def _model_payload(model: ModelSpec) -> dict:
    health = model_health_registry.get(model.key)
    return {
        "key": model.key,
        "model_id": model.model_id,
        "provider": model.provider,
        "tier": model.tier,
        "description": model.description,
        "capabilities": sorted(model.capabilities),
        "reasoning_levels": sorted(model.reasoning_levels),
        "context_window": model.context_window,
        "supports_tools": model.supports_tools,
        "cost_score": model.cost_score,
        "latency_score": model.latency_score,
        "health": {
            "available": health.available,
            "consecutive_failures": health.consecutive_failures,
            "last_error": health.last_error,
            "latency_ms": health.latency_ms,
        },
    }


@app.get("/api/v1/models")
def list_models() -> list[dict]:
    """Expose safe model capability metadata without credentials or provider secrets."""
    return [_model_payload(model) for model in model_registry.all()]


@app.get("/api/v1/models/health")
def list_model_health() -> dict:
    return {
        "models": [
            {
                "key": health.key,
                "provider": health.provider,
                "available": health.available,
                "consecutive_failures": health.consecutive_failures,
                "last_error": health.last_error,
                "latency_ms": health.latency_ms,
            }
            for health in model_health_registry.all()
        ]
    }


@app.get("/api/v1/models/{model_key}")
def get_model(model_key: str) -> dict:
    try:
        model = model_registry.get(model_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _model_payload(model)


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
        record = memory_store.remember(
            str(payload.get("content", "")),
            workspace_id=parsed_workspace,
            tags=tuple(tags),
            importance=float(payload.get("importance", 0.5)),
            memory_kind=MemoryKind(str(payload.get("memory_kind", "fact"))),
            source=str(payload.get("source", "user")),
            source_id=payload.get("source_id"),
        )
    except (TypeError, ValueError) as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _memory_payload(record)

@app.get("/api/v1/workspaces/{workspace_id}/memories")
def list_memories(workspace_id: UUID) -> list[dict]:
    _require_workspace(workspace_id)
    return [_memory_payload(record) for record in memory_store.list(workspace_id=workspace_id)]

@app.get("/api/v1/workspaces/{workspace_id}/memories/stats")
def memory_stats(workspace_id: UUID) -> dict:
    _require_workspace(workspace_id)
    return {"workspace_id": str(workspace_id), **memory_store.stats(workspace_id=workspace_id)}


@app.post("/api/v1/workspaces/{workspace_id}/memories/recall")
def recall_memories(workspace_id: UUID, payload: dict) -> dict:
    _require_workspace(workspace_id)
    query = str(payload.get("query", "")).strip()
    try: top_k = max(1, min(int(payload.get("top_k", 5)), 20))
    except (TypeError, ValueError) as exc: raise HTTPException(status_code=422, detail="top_k must be an integer") from exc
    try: matches = memory_store.recall_ranked(query, workspace_id=workspace_id, top_k=top_k)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"query": query, "workspace_id": str(workspace_id), "matches": [{**_memory_payload(match.record), "relevance": match.relevance, "confidence": match.confidence} for match in matches]}

@app.post("/api/v1/workspaces/{workspace_id}/memories/{memory_id}/archive")
def archive_memory(workspace_id: UUID, memory_id: UUID) -> dict:
    _require_workspace(workspace_id)
    try:
        record = memory_store.archive(memory_id, workspace_id=workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _memory_payload(record)


@app.post("/api/v1/workspaces/{workspace_id}/memories/{memory_id}/supersede")
def supersede_memory(workspace_id: UUID, memory_id: UUID, payload: dict) -> dict:
    _require_workspace(workspace_id)
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=422, detail="content is required")
    try:
        record = memory_store.supersede(
            memory_id,
            content,
            workspace_id=workspace_id,
            importance=float(payload["importance"]) if "importance" in payload else None,
            source=str(payload.get("source", "user")),
            source_id=payload.get("source_id"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 404, detail=str(exc)) from exc
    return _memory_payload(record)


@app.post("/api/v1/workspaces/{workspace_id}/memories/decay")
def decay_memories(workspace_id: UUID, payload: dict) -> dict:
    _require_workspace(workspace_id)
    try:
        records = memory_store.decay(
            workspace_id=workspace_id,
            older_than_days=int(payload.get("older_than_days", 30)),
            amount=float(payload.get("amount", 0.1)),
            minimum_importance=float(payload.get("minimum_importance", 0.0)),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"updated": [_memory_payload(record) for record in records]}


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

def _artifact_payload(artifact) -> dict:
    return {"artifact_id": str(artifact.artifact_id), "artifact_type": artifact.artifact_type, "filename": artifact.filename, "task_id": str(artifact.task_id) if artifact.task_id else None, "mime_type": artifact.mime_type, "size_bytes": artifact.size_bytes, "metadata": artifact.metadata, "created_at": artifact.created_at.isoformat()}


@app.post("/api/v1/artifacts", status_code=201)
async def create_artifact(file: UploadFile = File(...), task_id: UUID | None = None) -> dict:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=422, detail="filename cannot be empty")
    payload = await file.read()
    if len(payload) > settings.max_request_body_bytes:
        raise HTTPException(status_code=413, detail="artifact exceeds request size limit")
    artifact = artifact_store.put(payload, filename=filename, task_id=task_id, mime_type=file.content_type, metadata={"source": "user_upload"})
    artifact_registry.register(artifact)
    return _artifact_payload(artifact)


@app.get("/api/v1/artifacts")
def list_artifacts(task_id: UUID | None = None, limit: int = 50) -> list[dict]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    return [_artifact_payload(item) for item in artifact_registry.list(task_id=task_id, limit=limit)]


@app.get("/api/v1/artifacts/{artifact_id}")
def get_artifact(artifact_id: UUID) -> dict:
    try:
        return _artifact_payload(artifact_registry.get(artifact_id))
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: UUID) -> Response:
    try:
        artifact = artifact_registry.get(artifact_id)
        payload = artifact_store.get(artifact)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=payload, media_type=artifact.mime_type or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'})


@app.post("/api/v1/tasks/execute", response_model=ExecutionResponse, status_code=200)
def execute_task(payload: TaskCreate) -> ExecutionResponse:
    task = _build_task(payload)
    run, result = agent_runtime.run_engine(task, engine, budget=RunBudget(max_steps=32, max_tool_calls=64, max_retries=8))
    verification = result.verification
    run.metadata["result"] = {
        "model": result.model.model_id,
        "response_id": result.execution.response_id,
        "output": str(result.execution.output)[:50000],
        "verification_passed": bool(result.state.verification_passed),
        "verification_checks": list(verification.checks),
        "verification_issues": [str(item) for item in verification.issues],
        "grounding_score": verification.grounding_score,
        "tool_calls": len(result.execution.tool_calls),
        "events": [event.event_type.value for event in result.events],
    }
    artifact = artifact_store.put(result.execution.output.encode("utf-8"), filename="nexus-result.txt", artifact_type="execution-result", task_id=task.task_id, mime_type="text/plain; charset=utf-8", metadata={"verified": str(bool(result.state.verification_passed)), "run_id": str(run.run_id)})
    artifact_registry.register(artifact)
    run.metadata["result"]["artifact_id"] = str(artifact.artifact_id)
    agent_runtime._persist(run)
    return ExecutionResponse(
        run_id=str(run.run_id),
        task_id=str(task.task_id), model=result.model.model_id, response_id=result.execution.response_id, output=result.execution.output,
        verification_passed=result.state.verification_passed, verification_checks=verification.checks, verification_issues=list(verification.issues),
        grounding_score=verification.grounding_score,
        grounding=[{"citation": item.citation, "claim": item.claim, "overlap_score": item.overlap_score, "supported": item.supported} for item in verification.grounding],
        tool_calls=len(result.execution.tool_calls), events=[event.event_type.value for event in result.events], artifact_id=str(artifact.artifact_id),
    )

@app.get("/api/v1/runs/{run_id}")
def get_agent_run(run_id: str) -> dict:
    try:
        parsed_run_id = UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="run_id must be a UUID") from exc
    production_run = None
    agent_run = None
    try:
        production_run = production_runtime.status(parsed_run_id)
    except KeyError:
        pass
    try:
        agent_run = agent_runtime.get(parsed_run_id)
    except KeyError:
        pass
    run = agent_run if agent_run and agent_run.status.value in {"cancelled", "completed", "failed"} else production_run or agent_run
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
    return _run_payload(run)


@app.get("/api/v1/runs/{run_id}/stream")
def stream_agent_run(run_id: str):
    try:
        parsed_run_id = UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="run_id must be a UUID") from exc

    def events():
        last = None
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            production_run = None
            agent_run = None
            try:
                production_run = production_runtime.status(parsed_run_id)
            except KeyError:
                pass
            try:
                agent_run = agent_runtime.get(parsed_run_id)
            except KeyError:
                pass
            run = agent_run if agent_run and agent_run.status.value in {"cancelled", "completed", "failed"} else production_run or agent_run
            if run is None:
                yield "event: error\ndata: "+json.dumps({"detail": "unknown run"})+"\n\n"
                return
            payload = _run_payload(run)
            state = json.dumps(payload, sort_keys=True, default=str)
            if state != last:
                yield "event: run\ndata: "+state+"\n\n"
                last = state
                if payload["status"] in {"completed", "failed", "cancelled"}:
                    return
            else:
                yield ": heartbeat\n\n"
            time.sleep(0.5)
        yield "event: timeout\ndata: "+json.dumps({"run_id": run_id})+"\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/v1/runs")
def list_agent_runs() -> list[dict]:
    return [_run_payload(run) for run in agent_runtime.list_runs()]


@app.get("/api/v1/production/health")
def production_health() -> dict:
    runs = production_runtime.list_runs()
    active = sum(1 for run in runs if run.status.value in {"created", "running"})
    failed = sum(1 for run in runs if run.status.value == "failed")
    completed = sum(1 for run in runs if run.status.value == "completed")
    return {"status": "healthy", "runtime": production_runtime.health(), "runs": {"total": len(runs), "active": active, "completed": completed, "failed": failed}}


@app.post("/api/v1/production/tasks/execute", response_model=ExecutionResponse, status_code=200)
def execute_production_task(payload: TaskCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), x_user_id: str = Header(default="local-user", alias="X-User-Id")) -> ExecutionResponse:
    user_id = x_user_id.strip() or "local-user"
    try:
        product_catalog.consume_run(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    task = _build_task(payload)
    try:
        run, result = production_runtime.start(task, idempotency_key=idempotency_key, budget=RunBudget(max_steps=32, max_tool_calls=64, max_retries=8))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    verification = result.verification
    return ExecutionResponse(run_id=str(run.run_id), task_id=str(task.task_id), model=result.model.model_id, response_id=result.execution.response_id, output=result.execution.output, verification_passed=result.state.verification_passed, verification_checks=verification.checks, verification_issues=list(verification.issues), grounding_score=verification.grounding_score, grounding=[{"citation": item.citation, "claim": item.claim, "overlap_score": item.overlap_score, "supported": item.supported} for item in verification.grounding], tool_calls=len(result.execution.tool_calls), events=[event.event_type.value for event in result.events])


def _run_payload(run) -> dict:
    return {
        "run_id": str(run.run_id), "task_id": str(run.task_id) if run.task_id else None,
        "status": run.status.value, "task_status": run.task_status.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms, "steps_completed": run.steps_completed,
        "tool_calls": run.tool_calls, "retries": run.retries, "error": run.error,
        "metadata": run.metadata,
    }


@app.post("/api/v1/runs/{run_id}/cancel")
def cancel_agent_run(run_id: str) -> dict:
    try:
        parsed_run_id = UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="run_id must be a UUID") from exc
    try:
        try:
            run = agent_runtime.cancel(parsed_run_id)
        except KeyError:
            run = production_runtime.cancel(parsed_run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "run_id": str(run.run_id),
        "status": run.status.value,
        "task_status": run.task_status.value,
    }


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
async def upload_workspace_file(workspace_id: UUID, file: UploadFile = File(...), x_user_id: str = Header(default="local-user", alias="X-User-Id")) -> dict:
    _require_workspace(workspace_id); filename = Path(file.filename or "").name
    if not filename: raise HTTPException(status_code=422, detail="filename cannot be empty")
    user_id = x_user_id.strip() or "local-user"
    plan = next(item for item in product_catalog.plans() if item.plan_id == product_catalog.profile(user_id).plan_id)
    payload_bytes = await file.read()
    if len(payload_bytes) > plan.max_file_bytes:
        raise HTTPException(status_code=413, detail="file exceeds the active product plan limit")
    try:
        product_catalog.consume_file(user_id)
        file_ref = file_store.put(payload_bytes, filename=filename, workspace_id=workspace_id, mime_type=file.content_type); file_registry.register(file_ref); workspace_registry.context(workspace_id).add_file(file_ref.file_id)
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