from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4


class ArtifactNotFoundError(KeyError):
    """Raised when an artifact cannot be found in a store."""


@dataclass(frozen=True)
class Artifact:
    """A durable reference to an output produced by a NEXUS task."""

    artifact_id: UUID = field(default_factory=uuid4)
    artifact_type: str = "file"
    filename: str = "artifact"
    storage_key: str = ""
    task_id: UUID | None = None
    mime_type: str | None = None
    size_bytes: int = 0
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.artifact_type.strip():
            raise ValueError("artifact_type cannot be empty")
        if not self.filename.strip():
            raise ValueError("filename cannot be empty")
        if self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")


class LocalArtifactStore:
    """Simple filesystem-backed artifact store.

    This is the Phase 5 foundation. The interface is deliberately small so it
    can later be backed by S3-compatible object storage without changing the
    agent layer.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, storage_key: str) -> Path:
        if not storage_key or Path(storage_key).is_absolute():
            raise ValueError("storage_key must be a relative path")
        path = (self.root / storage_key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("storage_key escapes artifact store root")
        return path

    def put(
        self,
        data: bytes | bytearray | BinaryIO,
        *,
        filename: str,
        artifact_type: str = "file",
        task_id: UUID | None = None,
        mime_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Artifact:
        if not filename.strip():
            raise ValueError("filename cannot be empty")
        if isinstance(data, (bytes, bytearray)):
            payload = bytes(data)
        else:
            payload = data.read()
            if not isinstance(payload, bytes):
                raise TypeError("artifact stream must return bytes")

        artifact_id = uuid4()
        suffix = Path(filename).suffix
        storage_key = f"{artifact_id}{suffix}"
        path = self._safe_path(storage_key)
        path.write_bytes(payload)
        return Artifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            filename=Path(filename).name,
            storage_key=storage_key,
            task_id=task_id,
            mime_type=mime_type,
            size_bytes=len(payload),
            metadata=dict(metadata or {}),
        )

    def get(self, artifact: Artifact) -> bytes:
        path = self._safe_path(artifact.storage_key)
        if not path.is_file():
            raise ArtifactNotFoundError(str(artifact.artifact_id))
        return path.read_bytes()

    def exists(self, artifact: Artifact) -> bool:
        return self._safe_path(artifact.storage_key).is_file()
