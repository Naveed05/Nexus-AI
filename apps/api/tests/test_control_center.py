from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_control_center_summary_exposes_operational_surfaces() -> None:
    response = client.get("/api/v1/control-center/summary")
    assert response.status_code == 200
    body = response.json()

    assert body["overall_status"] in {"healthy", "degraded"}
    assert "deployment" in body
    assert "runtime" in body
    assert body["agents"]["count"] >= 1
    assert body["audit"]["valid"] is True
    assert body["models"]["count"] >= 1
    assert body["tools"]["count"] >= 1
    assert set(body["runs"]) >= {"total", "active", "completed", "failed", "recent"}


def test_control_center_frontend_surface_is_present() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="control-center-panel"' in response.text
    assert 'id="control-status"' in response.text
    assert 'id="control-run-count"' in response.text
