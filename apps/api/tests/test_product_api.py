from fastapi.testclient import TestClient

from nexus.api.main import app

client = TestClient(app)


def test_product_dashboard_contract() -> None:
    profile = client.get("/api/v1/product/profile")
    usage = client.get("/api/v1/product/usage")
    plans = client.get("/api/v1/product/plans")
    templates = client.get("/api/v1/product/templates")
    assert profile.status_code == usage.status_code == plans.status_code == templates.status_code == 200
    assert profile.json()["plan_id"] == "local"
    assert usage.json()["runs_limit"] == 100
    assert len(plans.json()) >= 2
    assert len(templates.json()) >= 4
