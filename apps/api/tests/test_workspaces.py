from uuid import uuid4

import pytest

from nexus.core.workspaces import WorkspaceNotFoundError, WorkspaceRegistry


def test_create_and_resolve_workspace():
    registry = WorkspaceRegistry()
    workspace = registry.create(
        name="Sales Intelligence",
        owner_id="user-1",
        metadata={"department": "analytics"},
    )

    assert registry.get(workspace.workspace_id) == workspace
    assert workspace.name == "Sales Intelligence"
    assert workspace.owner_id == "user-1"
    assert workspace.metadata["department"] == "analytics"
    assert len(registry.list()) == 1


def test_workspace_context_tracks_unique_resources():
    registry = WorkspaceRegistry()
    workspace = registry.create(name="Research")
    context = registry.context(workspace.workspace_id)

    file_id = uuid4()
    dataset_id = uuid4()
    artifact_id = uuid4()

    context.add_file(file_id)
    context.add_file(file_id)
    context.add_dataset(dataset_id)
    context.add_dataset(dataset_id)
    context.add_artifact(artifact_id)
    context.add_artifact(artifact_id)

    assert context.file_ids == [file_id]
    assert context.dataset_ids == [dataset_id]
    assert context.artifact_ids == [artifact_id]


def test_unknown_workspace_is_rejected():
    registry = WorkspaceRegistry()
    missing = uuid4()

    with pytest.raises(WorkspaceNotFoundError):
        registry.get(missing)

    with pytest.raises(WorkspaceNotFoundError):
        registry.context(missing)


def test_workspace_validation():
    registry = WorkspaceRegistry()

    with pytest.raises(ValueError, match="workspace name"):
        registry.create(name="   ")

    with pytest.raises(ValueError, match="owner_id"):
        registry.create(name="Valid", owner_id="   ")


def test_remove_workspace_also_removes_context():
    registry = WorkspaceRegistry()
    workspace = registry.create(name="Temporary")
    registry.context(workspace.workspace_id).add_dataset(uuid4())

    removed = registry.remove(workspace.workspace_id)

    assert removed == workspace
    assert registry.list() == ()
    with pytest.raises(WorkspaceNotFoundError):
        registry.context(workspace.workspace_id)
