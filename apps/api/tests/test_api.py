from uuid import UUID

from fastapi.testclient import TestClient

from nexus.api.main import app
from nexus.core.research import ResearchEngine, ResearchResult, ResearchSource
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
