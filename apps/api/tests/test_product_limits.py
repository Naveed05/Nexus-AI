from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_onboarding_contract() -> None:
    response = client.get("/api/v1/product/onboarding")
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_id"] == "local"
    assert {step["id"] for step in payload["steps"]} >= {"workspace", "template", "execution", "memory"}


def test_file_limit_is_reported_in_usage() -> None:
    response = client.get("/api/v1/product/usage")
    assert response.status_code == 200
    assert response.json()["files_limit"] == 100
