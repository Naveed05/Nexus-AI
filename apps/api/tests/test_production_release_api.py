from fastapi.testclient import TestClient

from nexus.api.main import app


client = TestClient(app)


def test_production_release_manifest_api():
    response = client.get("/api/v1/production/release")
    assert response.status_code == 200
    body = response.json()
    assert body["version"]
    assert body["release_id"].startswith(body["version"] + "+")
    assert "configuration_issues" in body
    assert "beta_access_key" not in response.text


def test_ready_includes_release_contract():
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "nexus-api"
    assert "release" in body
    assert "release_configuration" in body["checks"]
    assert body["release"]["release_id"].startswith(body["release"]["version"] + "+")
