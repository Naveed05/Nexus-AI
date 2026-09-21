from fastapi.testclient import TestClient
from nexus.api.main import app

client = TestClient(app)

def test_agent_catalog_api():
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    assert any(item["agent_id"] == "researcher" for item in response.json())

def test_collaboration_api_builds_workstreams():
    response = client.post("/api/v1/agents/collaborate", json={
        "objective":"prepare verified brief",
        "requests":[
            {"objective":"collect evidence","required_capability":"research","requester":"supervisor"},
            {"objective":"verify","required_capability":"verification","requester":"supervisor"},
        ],
    })
    assert response.status_code == 200
    assert len(response.json()["workstreams"]) == 2
    assert response.json()["approval_required"] is True
