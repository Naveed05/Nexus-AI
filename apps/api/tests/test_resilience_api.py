from fastapi.testclient import TestClient

from nexus.api.main import app


def test_resilience_backup_list_api():
    client = TestClient(app)
    response = client.get("/api/v1/resilience/backups")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_resilience_backup_validation_is_bounded():
    client = TestClient(app)
    response = client.get("/api/v1/resilience/backups?limit=0")
    assert response.status_code == 400
