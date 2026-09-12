from uuid import UUID

from nexus.api.main import _build_task, client, file_registry, workspace_registry
from nexus.core.schemas import TaskCreate


def test_workspace_task_receives_resource_context() -> None:
    workspace = workspace_registry.create(name="Analytics")
    upload = client.post(
        f"/api/v1/workspaces/{workspace.workspace_id}/files",
        files={"file": ("notes.txt", b"workspace notes", "text/plain")},
    )
    assert upload.status_code == 201
    file_id = UUID(upload.json()["file_id"])

    task = _build_task(TaskCreate(objective="Use the workspace file", workspace_id=workspace.workspace_id))

    assert task.workspace_id == workspace.workspace_id
    assert f"workspace_id: {workspace.workspace_id}" in (task.context or "")
    assert str(file_id) in (task.context or "")


def test_task_rejects_unknown_workspace() -> None:
    unknown = UUID("00000000-0000-0000-0000-000000000001")
    response = client.post(
        "/api/v1/tasks",
        json={"objective": "Inspect workspace", "workspace_id": str(unknown)},
    )
    assert response.status_code == 404


def test_workspace_task_response_exposes_workspace_id() -> None:
    workspace = workspace_registry.create(name="Research")
    response = client.post(
        "/api/v1/tasks",
        json={"objective": "Summarize workspace", "workspace_id": str(workspace.workspace_id)},
    )

    assert response.status_code == 201
    assert response.json()["workspace_id"] == str(workspace.workspace_id)


def test_workspace_file_lifecycle_and_isolation() -> None:
    workspace = workspace_registry.create(name="Files")
    other_workspace = workspace_registry.create(name="Other")

    upload = client.post(
        f"/api/v1/workspaces/{workspace.workspace_id}/files",
        files={"file": ("report.txt", b"hello nexus", "text/plain")},
    )
    assert upload.status_code == 201
    file_id = UUID(upload.json()["file_id"])

    listed = client.get(f"/api/v1/workspaces/{workspace.workspace_id}/files")
    assert listed.status_code == 200
    assert listed.json()[0]["file_id"] == str(file_id)
    assert listed.json()[0]["filename"] == "report.txt"

    downloaded = client.get(
        f"/api/v1/workspaces/{workspace.workspace_id}/files/{file_id}"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"hello nexus"
    assert downloaded.headers["content-type"].startswith("text/plain")

    denied = client.get(
        f"/api/v1/workspaces/{other_workspace.workspace_id}/files/{file_id}"
    )
    assert denied.status_code == 404

    deleted = client.delete(
        f"/api/v1/workspaces/{workspace.workspace_id}/files/{file_id}"
    )
    assert deleted.status_code == 204
    assert file_id not in workspace_registry.context(workspace.workspace_id).file_ids
    assert file_id not in {item.file_id for item in file_registry.list()}

    missing = client.get(
        f"/api/v1/workspaces/{workspace.workspace_id}/files/{file_id}"
    )
    assert missing.status_code == 404
