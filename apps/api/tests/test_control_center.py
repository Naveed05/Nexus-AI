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

def test_agent_workspace_surface_contract_is_present() -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    for marker in (
        'href="#agent-workspace"',
        'id="agent-workspace"',
        'id="live-run-title"',
        'id="run-timeline"',
        'id="cancel-run-btn"',
        'id="collab-objective"',
        'id="build-collab-btn"',
        'id="workspace-run-list"',
    ):
        assert marker in html

def test_agent_workspace_assets_expose_live_control_contract() -> None:
    script = client.get("/web/app.js")
    styles = client.get("/web/styles.css")
    assert script.status_code == 200
    assert "/api/v1/runs/" in script.text
    assert "/api/v1/agents/collaborate" in script.text
    assert "/cancel" in script.text
    assert "inspectRun" in script.text
    assert styles.status_code == 200
    assert ".workspace-command-grid" in styles.text
    assert ".run-timeline" in styles.text


def test_phase_39_frontend_polish_contract_is_present() -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    for marker in (
        'class="skip-link"',
        'id="boot-screen"',
        'id="main-content"',
        'aria-live="polite"',
    ):
        assert marker in html


def test_phase_39_frontend_resilience_and_accessibility_assets() -> None:
    script = client.get("/web/app.js")
    styles = client.get("/web/styles.css")
    assert script.status_code == 200
    for marker in (
        "Promise.allSettled",
        "unhandledrejection",
        "ArrowDown",
        "setStatusPill",
    ):
        assert marker in script.text
    assert styles.status_code == 200
    for marker in (
        ".skip-link",
        ".boot-screen",
        "prefers-reduced-motion",
        "focus-visible",
        ".workspace-run-row",
    ):
        assert marker in styles.text


def test_phase_39_product_controls_are_present() -> None:
    response = client.get("/")
    html = response.text
    for marker in (
        'id="copy-result-btn"',
        'id="run-filter"',
        'id="install-btn"',
        'mobile-web-app-capable',
        '/web/icon.svg',
    ):
        assert marker in html

    script = client.get("/web/app.js").text
    for marker in (
        "navigator.clipboard",
        "beforeinstallprompt",
        "serviceWorker.register",
        'confirm("Cancel this active NEXUS run?")',
    ):
        assert marker in script
