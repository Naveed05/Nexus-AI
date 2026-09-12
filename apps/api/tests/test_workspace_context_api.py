from io import BytesIO
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
