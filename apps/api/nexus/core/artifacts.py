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


class ArtifactRegistry:
    """Durable metadata index for produced artifacts."""

    def __init__(self, db_path: str | Path = ".nexus/artifacts.sqlite3") -> None:
        import sqlite3
        from threading import RLock
        self._sqlite3 = sqlite3
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY, artifact_type TEXT NOT NULL, filename TEXT NOT NULL,
            storage_key TEXT NOT NULL, task_id TEXT, mime_type TEXT, size_bytes INTEGER NOT NULL,
            metadata TEXT NOT NULL, created_at TEXT NOT NULL)""")
        self._conn.commit()

    def register(self, artifact: Artifact) -> Artifact:
        import json
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)",
                (str(artifact.artifact_id), artifact.artifact_type, artifact.filename, artifact.storage_key,
                 str(artifact.task_id) if artifact.task_id else None, artifact.mime_type, artifact.size_bytes,
                 json.dumps(artifact.metadata, sort_keys=True), artifact.created_at.isoformat()),
            )
            self._conn.commit()
        return artifact

    def get(self, artifact_id: UUID) -> Artifact:
        import json
        with self._lock:
            row = self._conn.execute("SELECT * FROM artifacts WHERE artifact_id=?", (str(artifact_id),)).fetchone()
        if row is None:
            raise ArtifactNotFoundError(str(artifact_id))
        return Artifact(artifact_id=UUID(row[0]), artifact_type=row[1], filename=row[2], storage_key=row[3],
                        task_id=UUID(row[4]) if row[4] else None, mime_type=row[5], size_bytes=row[6],
                        metadata=json.loads(row[7]), created_at=datetime.fromisoformat(row[8]))

    def list(self, *, task_id: UUID | None = None, limit: int = 50) -> tuple[Artifact, ...]:
        with self._lock:
            if task_id:
                rows = self._conn.execute("SELECT artifact_id FROM artifacts WHERE task_id=? ORDER BY created_at DESC LIMIT ?", (str(task_id), limit)).fetchall()
            else:
                rows = self._conn.execute("SELECT artifact_id FROM artifacts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return tuple(self.get(UUID(row[0])) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
