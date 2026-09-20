from uuid import UUID

from fastapi.testclient import TestClient

from nexus.api.main import agent_runtime, app
from nexus.core.research import ResearchEngine, ResearchResult, ResearchSource
from nexus.core.task import Task
from nexus.core.workspaces import workspace_registry

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_task_builds_domain_object() -> None:
    response = client.post("/api/v1/tasks", json={"objective": "Analyze my dataset", "context": "Sales analytics project", "capabilities": ["data_analysis", "visualization"], "constraints": ["Use Python"], "risk_level": "medium", "budget": 5.0})
    assert response.status_code == 201
    body = response.json()
    UUID(body["task_id"])
    assert body["objective"] == "Analyze my dataset"
    assert body["status"] == "pending"
    assert body["risk_level"] == "medium"
    assert body["capabilities"] == ["data_analysis", "visualization"]
    assert body["selected_model"] == "gpt-5.6-sol"
    assert body["created_at"]


def test_hard_task_routes_to_astra() -> None:
    response = client.post("/api/v1/tasks", json={"objective": "Debug this complex agent architecture"})
    assert response.status_code == 201
    assert response.json()["selected_model"] == "gpt-6-astra"


def test_low_budget_task_routes_to_luna() -> None:
    response = client.post("/api/v1/tasks", json={"objective": "Summarize these notes", "budget": 1.0})
    assert response.status_code == 201
    assert response.json()["selected_model"] == "gpt-5.6-luna"


def test_create_task_defaults() -> None:
    response = client.post("/api/v1/tasks", json={"objective": "Write a short summary"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["risk_level"] == "low"
    assert body["capabilities"] == []
    assert body["selected_model"] == "gpt-5.6-terra"


def test_create_task_rejects_empty_objective() -> None:
    response = client.post("/api/v1/tasks", json={"objective": ""})
    assert response.status_code == 422


def test_upload_dataset_returns_stable_reference() -> None:
    response = client.post("/api/v1/datasets", files={"file": ("sales.csv", b"name,value\na,10\nb,20\n", "text/csv")})
    assert response.status_code == 201
    body = response.json()
    UUID(body["dataset_id"])
    UUID(body["artifact_id"])
    assert body["filename"] == "sales.csv"
    assert body["file_format"] == "csv"
    assert body["size_bytes"] == len(b"name,value\na,10\nb,20\n")


def test_upload_dataset_rejects_unsupported_format() -> None:
    response = client.post("/api/v1/datasets", files={"file": ("sales.xml", b"<sales />", "application/xml")})
    assert response.status_code == 415


def test_research_endpoint_returns_structured_cited_evidence(monkeypatch) -> None:
    workspace = workspace_registry.create(name="Research API Test")
    source = ResearchSource("notes.md — chunk 1", "doc-1", "chunk-1", "Evidence text", 0.95, "AI safety")
    expected = ResearchResult("AI safety", ("AI safety",), (source,), ResearchEngine.plan_queries("AI safety", 1))

    def fake_research(question: str, *, workspace_id=None):
        assert question == "AI safety"
        assert workspace_id == workspace.workspace_id
        return expected

    monkeypatch.setattr("nexus.api.main.research_engine.research", fake_research)
    response = client.post("/api/v1/research", json={"question": "AI safety", "workspace_id": str(workspace.workspace_id), "max_queries": 1, "results_per_query": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_id"] == str(workspace.workspace_id)
    assert body["evidence_count"] == 1
    assert body["source_count"] == 1
    assert body["document_count"] == 1
    assert body["sources"][0]["citation"] == "notes.md — chunk 1"
    assert body["synthesis"]["context"]


def test_research_endpoint_rejects_unknown_workspace() -> None:
    response = client.post("/api/v1/research", json={"question": "AI safety", "workspace_id": str(UUID(int=0))})
    assert response.status_code == 404


def test_memory_api_is_workspace_scoped_and_supports_recall_lifecycle() -> None:
    workspace = workspace_registry.create(name="Memory API Test")
    other_workspace = workspace_registry.create(name="Other Memory API Test")

    created = client.post("/api/v1/memories", json={"workspace_id": str(workspace.workspace_id), "content": "Use deterministic pytest checks", "tags": ["Testing"], "importance": 0.8})
    assert created.status_code == 201
    memory = created.json()
    assert memory["tags"] == ["testing"]

    other = client.post("/api/v1/memories", json={"workspace_id": str(other_workspace.workspace_id), "content": "Use pytest checks", "importance": 1.0})
    assert other.status_code == 201

    listed = client.get(f"/api/v1/workspaces/{workspace.workspace_id}/memories")
    assert listed.status_code == 200
    assert [item["memory_id"] for item in listed.json()] == [memory["memory_id"]]

    recalled = client.post(f"/api/v1/workspaces/{workspace.workspace_id}/memories/recall", json={"query": "deterministic pytest"})
    assert recalled.status_code == 200
    assert recalled.json()["matches"][0]["memory_id"] == memory["memory_id"]
    assert recalled.json()["matches"][0]["confidence"] > 0

    deleted = client.delete(f"/api/v1/workspaces/{workspace.workspace_id}/memories/{memory['memory_id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/workspaces/{workspace.workspace_id}/memories").json() == []


def test_memory_api_rejects_unknown_workspace() -> None:
    response = client.get(f"/api/v1/workspaces/{UUID(int=0)}/memories")
    assert response.status_code == 404



def test_byok_credential_lifecycle_is_user_scoped_and_masks_keys() -> None:
    user_a = "byok-test-user-a"
    user_b = "byok-test-user-b"
    configured = client.put(
        "/api/v1/byok/credentials/openai",
        headers={"X-Nexus-User-ID": user_a},
        json={"api_key": "sk-test-secret-1234"},
    )
    assert configured.status_code == 200
    body = configured.json()
    assert body["configured"] is True
    assert body["masked_key"] == "sk-t••••••••1234"
    assert "sk-test-secret-1234" not in configured.text

    status_a = client.get("/api/v1/byok/credentials", headers={"X-Nexus-User-ID": user_a})
    status_b = client.get("/api/v1/byok/credentials", headers={"X-Nexus-User-ID": user_b})
    assert status_a.status_code == 200
    assert status_b.status_code == 200
    assert next(item for item in status_a.json()["providers"] if item["provider"] == "openai")["configured"] is True
    assert next(item for item in status_b.json()["providers"] if item["provider"] == "openai")["configured"] is False

    removed = client.delete(
        "/api/v1/byok/credentials/openai",
        headers={"X-Nexus-User-ID": user_a},
    )
    assert removed.status_code == 204


def test_byok_generate_uses_user_credential_without_exposing_it(monkeypatch) -> None:
    from nexus.api.main import byok_provider_manager
    from nexus.core.models import ModelResponse

    user_id = "byok-generate-user"
    byok_provider_manager.configure(user_id, "groq", "groq-secret-1234")

    def fake_generate(**kwargs):
        assert kwargs["user_id"] == user_id
        assert kwargs["model"].provider == "groq"
        assert kwargs["model"].model_id == "llama-3.3-70b-versatile"
        assert kwargs["input_items"][0]["content"] == "Hello NEXUS"
        return ModelResponse(
            output="Hello from Groq",
            response_id="test-response",
            provider="groq",
            model_id="llama-3.3-70b-versatile",
        )

    monkeypatch.setattr(byok_provider_manager, "generate", fake_generate)
    response = client.post(
        "/api/v1/byok/generate",
        headers={"X-Nexus-User-ID": user_id},
        json={
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "prompt": "Hello NEXUS",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "response_id": "test-response",
        "output": "Hello from Groq",
    }
    assert "groq-secret-1234" not in response.text


def test_byok_requires_user_identity() -> None:
    response = client.get("/api/v1/byok/credentials")
    assert response.status_code == 401


def test_agent_run_lifecycle_endpoints() -> None:
    task = Task(objective="API runtime lifecycle")
    run = agent_runtime.create_run(task)

    status = client.get(f"/api/v1/runs/{run.run_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "created"

    cancelled = client.post(f"/api/v1/runs/{run.run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    final = client.get(f"/api/v1/runs/{run.run_id}")
    assert final.json()["task_status"] == "cancelled"


def test_agent_run_endpoint_rejects_unknown_run() -> None:
    response = client.get("/api/v1/runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_agent_run_list_endpoint_includes_created_run() -> None:
    from nexus.api.main import agent_runtime

    task = Task(objective="list runtime runs")
    run = agent_runtime.create_run(task)
    response = client.get("/api/v1/runs")
    assert response.status_code == 200
    payload = response.json()
    match = next(item for item in payload if item["run_id"] == str(run.run_id))
    assert match["task_id"] == str(task.task_id)
    assert match["status"] == "created"
