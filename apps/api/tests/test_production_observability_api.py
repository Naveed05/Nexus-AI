from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_readiness_and_metrics_endpoints() -> None:
    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert "nexus_http_requests_total" in metrics.text


def test_request_id_is_returned_and_can_be_provided() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]

    supplied = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-123"})
    assert supplied.headers["X-Request-ID"] == "test-request-123"
