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
    assert body["selected_model"] == "gpt-5.6-sol"
    assert body["created_at"]


def test_hard_task_routes_to_astra() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"objective": "Debug this complex agent architecture"},
    )

    assert response.status_code == 201
    assert response.json()["selected_model"] == "gpt-6-astra"


def test_low_budget_task_routes_to_luna() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"objective": "Summarize these notes", "budget": 1.0},
    )

    assert response.status_code == 201
    assert response.json()["selected_model"] == "gpt-5.6-luna"


def test_create_task_defaults() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"objective": "Write a short summary"},
    )

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
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("sales.csv", b"name,value\na,10\nb,20\n", "text/csv")},
    )

    assert response.status_code == 201
    body = response.json()
    UUID(body["dataset_id"])
    UUID(body["artifact_id"])
    assert body["filename"] == "sales.csv"
    assert body["file_format"] == "csv"
    assert body["size_bytes"] == len(b"name,value\na,10\nb,20\n")


def test_upload_dataset_rejects_unsupported_format() -> None:
    response = client.post(
        "/api/v1/datasets",
        files={"file": ("sales.xml", b"<sales />", "application/xml")},
    )
    assert response.status_code == 415
