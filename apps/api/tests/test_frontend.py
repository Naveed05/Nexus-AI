from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_frontend_homepage_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "NEXUS AI" in response.text
    assert 'src="/web/app.js"' in response.text


def test_frontend_assets_are_served() -> None:
    script = client.get("/web/app.js")
    styles = client.get("/web/styles.css")
    assert script.status_code == 200
    assert "api/v1/production/health" in script.text
    assert styles.status_code == 200
    assert ".workspace-grid" in styles.text
