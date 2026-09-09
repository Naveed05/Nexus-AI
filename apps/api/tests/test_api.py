from uuid import UUID

from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_task_builds_domain_object() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={
            "objective": "Analyze my dataset",
            "context": "Sales analytics project",
            "capabilities": ["data_analysis", "visualization"],
            "constraints": ["Use Python"],
            "risk_level": "medium",
            "budget": 5.0,
        },
    )

    assert response.status_code == 201
    body = response.json()
    UUID(body["task_id"])
    assert body["objective"] == "Analyze my dataset"
    assert body["status"] == "pending"
    assert body["risk_level"] == "medium"
    assert body["capabilities"] == ["data_analysis", "visualization"]
    assert body["created_at"]


def test_create_task_defaults() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"objective": "Research AI agents"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["risk_level"] == "low"
    assert body["capabilities"] == []


def test_create_task_rejects_empty_objective() -> None:
    response = client.post("/api/v1/tasks", json={"objective": ""})
    assert response.status_code == 422
