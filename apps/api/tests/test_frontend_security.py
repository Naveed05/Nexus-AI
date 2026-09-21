from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_frontend_security_headers_are_present() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_frontend_manifest_is_served() -> None:
    response = client.get("/web/manifest.webmanifest")
    assert response.status_code == 200
    assert response.json()["short_name"] == "NEXUS"
