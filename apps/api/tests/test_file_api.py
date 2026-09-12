from uuid import UUID

from fastapi.testclient import TestClient

from nexus.api.main import app, file_store

client = TestClient(app)


def test_workspace_lifecycle() -> None:
    response = client.post("/api/v1/workspaces", json={"name": "Research", "owner_id": "user-1"})
    assert response.status_code == 201
    body = response.json()
    workspace_id = UUID(body["workspace_id"])
    assert body["name"] == "Research"
    assert body["owner_id"] == "user-1"

    listed = client.get("/api/v1/workspaces")
    assert listed.status_code == 200
    assert any(item["workspace_id"] == str(workspace_id) for item in listed.json())

    fetched = client.get(f"/api/v1/workspaces/{workspace_id}")
    assert fetched.status_code == 200
    assert fetched.json()["workspace_id"] == str(workspace_id)


def test_workspace_file_upload_list_download_and_delete() -> None:
    workspace = client.post("/api/v1/workspaces", json={"name": "Files"}).json()
    workspace_id = UUID(workspace["workspace_id"])
    payload = b"hello nexus\n"

    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/files",
        files={"file": ("notes.txt", payload, "text/plain")},
    )
    assert uploaded.status_code == 201
    body = uploaded.json()
    file_id = UUID(body["file_id"])
    assert body["workspace_id"] == str(workspace_id)
    assert body["filename"] == "notes.txt"
    assert body["size_bytes"] == len(payload)

    listed = client.get(f"/api/v1/workspaces/{workspace_id}/files")
    assert listed.status_code == 200
    assert [item["file_id"] for item in listed.json()] == [str(file_id)]

    downloaded = client.get(f"/api/v1/workspaces/{workspace_id}/files/{file_id}")
    assert downloaded.status_code == 200
    assert downloaded.content == payload
    assert "attachment" in downloaded.headers["content-disposition"]

    file_ref = next(item for item in listed.json() if item["file_id"] == str(file_id))
    assert file_store._safe_path(f"{workspace_id}/{file_id}.txt").is_file()

    deleted = client.delete(f"/api/v1/workspaces/{workspace_id}/files/{file_id}")
    assert deleted.status_code == 204
    assert not file_store._safe_path(f"{workspace_id}/{file_id}.txt").exists()
    assert client.get(f"/api/v1/workspaces/{workspace_id}/files/{file_id}").status_code == 404
    assert client.get(f"/api/v1/workspaces/{workspace_id}/files").json() == []


def test_file_isolation_between_workspaces() -> None:
    workspace_a = UUID(client.post("/api/v1/workspaces", json={"name": "A"}).json()["workspace_id"])
    workspace_b = UUID(client.post("/api/v1/workspaces", json={"name": "B"}).json()["workspace_id"])
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_a}/files",
        files={"file": ("secret.txt", b"private", "text/plain")},
    )
    file_id = UUID(uploaded.json()["file_id"])

    assert client.get(f"/api/v1/workspaces/{workspace_b}/files/{file_id}").status_code == 404
    assert client.delete(f"/api/v1/workspaces/{workspace_b}/files/{file_id}").status_code == 404
    assert client.get(f"/api/v1/workspaces/{workspace_b}/files").json() == []


def test_unknown_workspace_returns_404() -> None:
    unknown = "00000000-0000-0000-0000-000000000001"
    assert client.get(f"/api/v1/workspaces/{unknown}").status_code == 404
    assert client.get(f"/api/v1/workspaces/{unknown}/files").status_code == 404


def test_upload_sanitizes_filename() -> None:
    workspace_id = UUID(client.post("/api/v1/workspaces", json={"name": "Safe"}).json()["workspace_id"])
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/files",
        files={"file": ("../../danger.txt", b"safe", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["filename"] == "danger.txt"
