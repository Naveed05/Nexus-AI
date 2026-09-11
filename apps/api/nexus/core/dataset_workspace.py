from __future__ import annotations

from pathlib import Path
from uuid import UUID

from nexus.core.artifacts import LocalArtifactStore
from nexus.core.data_engine import DataIntelligenceEngine
from nexus.core.datasets import DatasetRef, DatasetRegistry, register_dataset


class DatasetNotFoundError(KeyError):
    """Raised when a dataset reference cannot be resolved."""


class DatasetWorkspace:
    """Resolve registered dataset references into bytes or data frames.

    The workspace composes the Phase 5 artifact store and dataset registry.
    Keeping this boundary separate from tools lets the storage backend evolve
    without changing agent-facing tool contracts.
    """

    def __init__(self, root: str | Path) -> None:
        self.store = LocalArtifactStore(root)
        self.registry = DatasetRegistry()
        self.engine = DataIntelligenceEngine()

    def register(
        self,
        data: bytes,
        *,
        filename: str,
        file_format: str,
        metadata: dict | None = None,
    ) -> DatasetRef:
        dataset, _artifact = register_dataset(
            data,
            filename=filename,
            file_format=file_format,
            store=self.store,
            metadata=metadata,
        )
        return self.registry.register(dataset)

    def get(self, dataset_id: UUID) -> DatasetRef:
        try:
            return self.registry.get(dataset_id)
        except KeyError as exc:
            raise DatasetNotFoundError(str(dataset_id)) from exc

    def read_bytes(self, dataset_id: UUID) -> bytes:
        dataset = self.get(dataset_id)
        if dataset.artifact_id is None:
            raise DatasetNotFoundError(str(dataset_id))
        artifact = next(
            (
                artifact
                for artifact in (
                    self._artifact_for_dataset(dataset),
                )
                if artifact is not None
            ),
            None,
        )
        if artifact is None:
            raise DatasetNotFoundError(str(dataset_id))
        return self.store.get(artifact)

    def load(self, dataset_id: UUID):
        dataset = self.get(dataset_id)
        return self.engine.load_bytes(self.read_bytes(dataset_id), dataset.file_format)

    def _artifact_for_dataset(self, dataset: DatasetRef):
        if dataset.artifact_id is None:
            return None
        from nexus.core.artifacts import Artifact

        return Artifact(
            artifact_id=dataset.artifact_id,
            artifact_type="dataset",
            filename=dataset.filename,
            storage_key=f"{dataset.artifact_id}{Path(dataset.filename).suffix}",
            size_bytes=dataset.size_bytes,
        )
