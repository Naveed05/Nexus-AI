from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_frontend_exposes_intelligence_and_memory_surfaces() -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert 'id="model-grid"' in body
    assert 'id="capability-list"' in body
    assert 'id="memory-input"' in body
    assert 'id="recall-btn"' in body


def test_intelligence_contracts_are_available_to_frontend() -> None:
    models = client.get("/api/v1/models")
    capabilities = client.get("/api/v1/tools/capabilities")
    assert models.status_code == 200
    assert capabilities.status_code == 200
    assert models.json()
    assert capabilities.json()["capabilities"]
