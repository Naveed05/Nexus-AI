from fastapi.testclient import TestClient

from nexus.api.main import app


client = TestClient(app)


def test_workspace_intelligence_and_knowledge_api() -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "Phase 56 API", "owner_id": "api-test"},
    ).json()
    workspace_id = workspace["workspace_id"]

    upload = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("policy.txt", b"Verified retention applies to workspace artifacts.", "text/plain")},
    )
    assert upload.status_code == 201

    intelligence = client.get(f"/api/v1/workspaces/{workspace_id}/intelligence")
    assert intelligence.status_code == 200
    body = intelligence.json()
    assert body["readiness"]["has_searchable_knowledge"] is True

    search = client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge/search",
        json={"query": "verified retention", "top_k": 3},
    )
    assert search.status_code == 200
    assert search.json()["result_count"] >= 1


def test_dataset_science_api_contract() -> None:
    upload = client.post(
        "/api/v1/datasets",
        files={"file": ("customers.csv", b"age,target\n20,no\n25,no\n30,yes\n35,yes\n40,yes\n45,yes\n", "text/csv")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["dataset_id"]

    schema = client.get(f"/api/v1/datasets/{dataset_id}/schema")
    assert schema.status_code == 200
    assert schema.json()["rows"] == 6

    analysis = client.post(f"/api/v1/datasets/{dataset_id}/analyze", json={"target": "target"})
    assert analysis.status_code == 200
    assert analysis.json()["problem"]["target"] == "target"

    baseline = client.post(f"/api/v1/datasets/{dataset_id}/baseline", json={"target": "target"})
    assert baseline.status_code == 200
    assert "metrics" in baseline.json()
