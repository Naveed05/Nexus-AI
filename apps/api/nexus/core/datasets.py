from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
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
    """Dataset metadata registry backed by SQLite when a storage path is supplied."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._storage_path = Path(storage_path) if storage_path else None
        self._records: dict[UUID, DatasetRef] = {}
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        if self._storage_path:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self._storage_path, check_same_thread=False)
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_format TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    artifact_id TEXT,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self._connection.commit()
            self._load()

    def _load(self) -> None:
        assert self._connection is not None
        for row in self._connection.execute("SELECT * FROM datasets ORDER BY created_at"):
            self._records[UUID(row[0])] = DatasetRef(
                dataset_id=UUID(row[0]),
                filename=row[1],
                file_format=row[2],
                size_bytes=row[3],
                artifact_id=UUID(row[4]) if row[4] else None,
                metadata=json.loads(row[5] or "{}"),
                created_at=datetime.fromisoformat(row[6]),
            )

    def register(self, dataset: DatasetRef) -> DatasetRef:
        with self._lock:
            if dataset.dataset_id in self._records:
                raise ValueError(f"Dataset already registered: {dataset.dataset_id}")
            self._records[dataset.dataset_id] = dataset
            if self._connection is not None:
                self._connection.execute(
                    "INSERT INTO datasets VALUES (?,?,?,?,?,?,?)",
                    (
                        str(dataset.dataset_id),
                        dataset.filename,
                        dataset.file_format,
                        dataset.size_bytes,
                        str(dataset.artifact_id) if dataset.artifact_id else None,
                        json.dumps(dataset.metadata),
                        dataset.created_at.isoformat(),
                    ),
                )
                self._connection.commit()
            return dataset

    def get(self, dataset_id: UUID) -> DatasetRef:
        with self._lock:
            try:
                return self._records[dataset_id]
            except KeyError as exc:
                raise KeyError(f"Unknown dataset: {dataset_id}") from exc

    def list(self) -> tuple[DatasetRef, ...]:
        with self._lock:
            return tuple(self._records.values())

    def remove(self, dataset_id: UUID) -> DatasetRef:
        with self._lock:
            try:
                dataset = self._records.pop(dataset_id)
            except KeyError as exc:
                raise KeyError(f"Unknown dataset: {dataset_id}") from exc
            if self._connection is not None:
                self._connection.execute("DELETE FROM datasets WHERE dataset_id=?", (str(dataset_id),))
                self._connection.commit()
            return dataset


def register_dataset(
    data: bytes,
    *,
    filename: str,
    file_format: str,
    store: LocalArtifactStore,
    metadata: dict[str, Any] | None = None,
) -> tuple[DatasetRef, Artifact]:
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
