from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from nexus.core.artifacts import Artifact, LocalArtifactStore


@dataclass(frozen=True)
class DatasetRef:
    """Metadata reference for a dataset available to NEXUS tools."""

    dataset_id: UUID = field(default_factory=uuid4)
    filename: str = "dataset"
    file_format: str = "csv"
    size_bytes: int = 0
    artifact_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.filename.strip():
            raise ValueError("filename cannot be empty")
        normalized = self.file_format.lower().lstrip(".")
        if normalized not in {"csv", "parquet", "json"}:
            raise ValueError("file_format must be csv, parquet, or json")
        if self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        object.__setattr__(self, "file_format", normalized)


class DatasetRegistry:
    """In-memory dataset metadata registry for the Phase 5 foundation."""

    def __init__(self) -> None:
        self._datasets: dict[UUID, DatasetRef] = {}

    def register(self, dataset: DatasetRef) -> DatasetRef:
        if dataset.dataset_id in self._datasets:
            raise ValueError(f"Dataset already registered: {dataset.dataset_id}")
        self._datasets[dataset.dataset_id] = dataset
        return dataset

    def get(self, dataset_id: UUID) -> DatasetRef:
        try:
            return self._datasets[dataset_id]
        except KeyError as exc:
            raise KeyError(f"Unknown dataset: {dataset_id}") from exc

    def list(self) -> tuple[DatasetRef, ...]:
        return tuple(self._datasets.values())

    def remove(self, dataset_id: UUID) -> DatasetRef:
        try:
            return self._datasets.pop(dataset_id)
        except KeyError as exc:
            raise KeyError(f"Unknown dataset: {dataset_id}") from exc


def register_dataset(
    data: bytes,
    *,
    filename: str,
    file_format: str,
    store: LocalArtifactStore,
    metadata: dict[str, Any] | None = None,
) -> tuple[DatasetRef, Artifact]:
    """Persist dataset bytes and return its stable dataset/artifact references."""
    normalized = file_format.lower().lstrip(".")
    artifact = store.put(
        data,
        filename=Path(filename).name,
        artifact_type="dataset",
        metadata={"file_format": normalized},
    )
    dataset = DatasetRef(
        filename=Path(filename).name,
        file_format=normalized,
        size_bytes=artifact.size_bytes,
        artifact_id=artifact.artifact_id,
        metadata=dict(metadata or {}),
    )
    return dataset, artifact
