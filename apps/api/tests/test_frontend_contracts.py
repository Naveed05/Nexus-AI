from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_workspace_contract_supports_creation_and_listing() -> None:
    created = client.post("/api/v1/workspaces", json={"name": "Phase 25 UI Workspace"})
    assert created.status_code == 201
    workspace = created.json()
    listed = client.get("/api/v1/workspaces")
    assert listed.status_code == 200
    assert any(item["workspace_id"] == workspace["workspace_id"] for item in listed.json())


def test_frontend_contains_workspace_controls() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="workspace-select"' in response.text
    assert 'id="file-input"' in response.text
