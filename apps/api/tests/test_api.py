from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_task() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"objective": "Analyze my dataset"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "accepted"
