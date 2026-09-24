from pathlib import Path


def test_workflow_control_center_contract():
    web_root = Path(__file__).resolve().parents[2] / "web"
    app = (web_root / "app.js").read_text()
    index = (web_root / "index.html").read_text()
    for token in (
        "/api/v1/workflows/metrics",
        "/api/v1/workflows/",
        "data-wfc",
        "workflow-metric-total",
        "workflow-metric-failed",
    ):
        assert token in app or token in index
    assert "Workflow Control Center" in index
