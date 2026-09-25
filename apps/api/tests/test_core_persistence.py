from pathlib import Path
from uuid import uuid4

from nexus.core.datasets import DatasetRegistry, DatasetRef
from nexus.core.dataset_workspace import DatasetWorkspace
from nexus.core.workspaces import WorkspaceRegistry


def test_workspace_context_survives_registry_restart(tmp_path: Path) -> None:
    db = tmp_path / "workspaces.sqlite3"
    registry = WorkspaceRegistry(db.as_posix())
    workspace = registry.create(name="Persistent", owner_id="user-1", metadata={"team": "data"})
    context = registry.context(workspace.workspace_id)
    file_id, dataset_id, artifact_id, document_id = uuid4(), uuid4(), uuid4(), uuid4()
    context.add_file(file_id)
    context.add_dataset(dataset_id)
    context.add_artifact(artifact_id)
    context.add_document(document_id)
    registry.save_context(workspace.workspace_id)

    reopened = WorkspaceRegistry(db.as_posix())
    assert reopened.get(workspace.workspace_id).metadata == {"team": "data"}
    restored = reopened.context(workspace.workspace_id)
    assert restored.file_ids == [file_id]
    assert restored.dataset_ids == [dataset_id]
    assert restored.artifact_ids == [artifact_id]
    assert restored.document_ids == [document_id]


def test_dataset_registry_survives_restart(tmp_path: Path) -> None:
    db = tmp_path / "datasets.sqlite3"
    dataset = DatasetRef(filename="sales.csv", file_format="csv", size_bytes=12, metadata={"workspace_id": "w1"})
    DatasetRegistry(db).register(dataset)

    reopened = DatasetRegistry(db)
    assert reopened.get(dataset.dataset_id) == dataset
    assert reopened.list() == (dataset,)


def test_dataset_workspace_survives_restart(tmp_path: Path) -> None:
    root = tmp_path / "data"
    first = DatasetWorkspace(root)
    dataset = first.register(b"name,value\na,1\n", filename="sample.csv", file_format="csv")
    second = DatasetWorkspace(root)
    assert second.get(dataset.dataset_id).filename == "sample.csv"
    assert second.read_bytes(dataset.dataset_id) == b"name,value\na,1\n"
