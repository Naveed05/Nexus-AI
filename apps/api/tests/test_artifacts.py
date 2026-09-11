from uuid import uuid4

import pytest

from nexus.core.artifacts import Artifact, ArtifactNotFoundError, LocalArtifactStore
from nexus.core.datasets import DatasetRef, DatasetRegistry, register_dataset
from nexus.core.state import AgentState


def test_artifact_validation_rejects_invalid_values():
    with pytest.raises(ValueError, match="artifact_type"):
        Artifact(artifact_type="")
    with pytest.raises(ValueError, match="filename"):
        Artifact(filename="")
    with pytest.raises(ValueError, match="size_bytes"):
        Artifact(size_bytes=-1)


def test_local_artifact_store_round_trip(tmp_path):
    store = LocalArtifactStore(tmp_path)
    artifact = store.put(b"hello nexus", filename="result.csv", artifact_type="dataset")

    assert artifact.filename == "result.csv"
    assert artifact.size_bytes == 11
    assert artifact.storage_key.endswith(".csv")
    assert store.exists(artifact)
    assert store.get(artifact) == b"hello nexus"


def test_local_artifact_store_rejects_path_escape(tmp_path):
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="relative"):
        store._safe_path("/outside.txt")
    with pytest.raises(ValueError, match="escapes"):
        store._safe_path("../outside.txt")


def test_local_artifact_store_missing_artifact(tmp_path):
    store = LocalArtifactStore(tmp_path)
    artifact = Artifact(storage_key="missing.bin")
    with pytest.raises(ArtifactNotFoundError):
        store.get(artifact)


def test_dataset_ref_normalizes_format_and_validates():
    dataset = DatasetRef(filename="data.csv", file_format=".CSV", size_bytes=5)
    assert dataset.file_format == "csv"

    with pytest.raises(ValueError, match="file_format"):
        DatasetRef(file_format="xml")
    with pytest.raises(ValueError, match="size_bytes"):
        DatasetRef(size_bytes=-1)


def test_dataset_registry_register_get_list_and_remove():
    registry = DatasetRegistry()
    dataset = DatasetRef(filename="data.csv")
    assert registry.register(dataset) == dataset
    assert registry.get(dataset.dataset_id) == dataset
    assert registry.list() == (dataset,)
    assert registry.remove(dataset.dataset_id) == dataset
    with pytest.raises(KeyError, match="Unknown dataset"):
        registry.get(dataset.dataset_id)


def test_dataset_registry_rejects_duplicate_id():
    registry = DatasetRegistry()
    dataset_id = uuid4()
    registry.register(DatasetRef(dataset_id=dataset_id))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(DatasetRef(dataset_id=dataset_id))


def test_register_dataset_persists_bytes_and_links_artifact(tmp_path):
    store = LocalArtifactStore(tmp_path)
    dataset, artifact = register_dataset(
        b"name,value\na,1\n",
        filename="sample.csv",
        file_format="CSV",
        store=store,
        metadata={"source": "test"},
    )

    assert dataset.artifact_id == artifact.artifact_id
    assert dataset.size_bytes == artifact.size_bytes
    assert dataset.metadata == {"source": "test"}
    assert store.get(artifact).startswith(b"name,value")


def test_agent_state_add_artifact_is_idempotent():
    task_id = uuid4()
    state = AgentState(task_id=task_id, objective="create an artifact")
    artifact_id = uuid4()

    state.add_artifact(artifact_id)
    state.add_artifact(str(artifact_id))

    assert state.artifacts == [str(artifact_id)]
    with pytest.raises(ValueError, match="artifact_id"):
        state.add_artifact("")
