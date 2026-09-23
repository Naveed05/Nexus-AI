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


def test_phase_40_runtime_bridge_exposes_live_stream_and_result_contract() -> None:
    response = client.get("/api/v1/runs/not-a-uuid/stream")
    assert response.status_code == 422

    health = client.get("/api/v1/production/health")
    assert health.status_code == 200
    assert "runtime" in health.json()

    script = client.get("/web/app.js").text
    for marker in (
        "/api/v1/runs/",
        "/stream",
        "EventSource",
        "workspace_id:state.workspace",
        "renderRunResult",
    ):
        assert marker in script


def test_phase_40_runtime_control_uses_production_boundary() -> None:
    main_source = client.get("/openapi.json")
    assert main_source.status_code == 200
    paths = main_source.json()["paths"]
    assert "/api/v1/runs/{run_id}" in paths
    assert "/api/v1/runs/{run_id}/stream" in paths
    assert "/api/v1/runs/{run_id}/cancel" in paths


def test_phase_41_artifact_delivery_contract() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/artifacts" in paths
    assert "/api/v1/artifacts/{artifact_id}/download" in paths

    script = client.get("/web/app.js").text
    html = client.get("/").text
    for marker in ("renderArtifactDelivery", "/api/v1/artifacts/", "download-artifact-btn"):
        assert marker in script or marker in html
    assert 'id="artifact-status"' in html


def test_phase_42_durable_job_api_contract_is_present() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/v1/jobs",
        "/api/v1/jobs/summary",
        "/api/v1/jobs/{job_id}",
        "/api/v1/jobs/{job_id}/cancel",
        "/api/v1/jobs/{job_id}/pause",
        "/api/v1/jobs/{job_id}/resume",
        "/api/v1/jobs/{job_id}/retry",
        "/api/v1/jobs/{job_id}/stream",
    ):
        assert path in paths


def test_phase_42_job_center_frontend_contract() -> None:
    html = client.get("/").text
    script = client.get("/web/app.js").text
    styles = client.get("/web/styles.css").text
    for marker in ('href="#jobs"', 'id="jobs"', 'id="job-list"', 'id="job-summary"', 'id="jobs-refresh"'):
        assert marker in html
    for marker in ("/api/v1/jobs", "EventSource", "inspectJob", "loadJobs"):
        assert marker in script
    assert ".job-row" in styles
