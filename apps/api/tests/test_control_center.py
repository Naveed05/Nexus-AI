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

def test_premium_frontend_surface_contract_is_present() -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    for marker in (
        'id="sidebar"', 'id="task-input"', 'id="workspace-select"',
        'id="agent-grid"', 'id="runs-list"', 'id="knowledge-detail"',
        'id="control-center"', 'id="command-modal"', 'id="theme-btn"',
        'src="/web/app.js"', 'href="/web/styles.css"',
    ):
        assert marker in html

def test_frontend_has_required_navigation_surfaces() -> None:
    response = client.get("/")
    html = response.text
    for section in ("overview", "workspace", "agents", "runs", "knowledge", "control-center"):
        assert 'href="#'+section+'"' in html
        assert 'id="'+section+'"' in html
