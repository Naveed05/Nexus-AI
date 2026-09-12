from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4


class FileNotFoundError(KeyError):
    """Raised when a workspace file cannot be resolved."""


@dataclass(frozen=True)
class FileRef:
    """Stable metadata reference for a file stored by NEXUS."""

    file_id: UUID = field(default_factory=uuid4)
    workspace_id: UUID | None = None
    filename: str = "file"
    storage_key: str = ""
    mime_type: str | None = None
    size_bytes: int = 0
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.filename.strip():
            raise ValueError("filename cannot be empty")
        if self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")


class LocalFileStore:
    """Secure filesystem-backed storage for workspace files."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, storage_key: str) -> Path:
        if not storage_key or Path(storage_key).is_absolute():
            raise ValueError("storage_key must be a relative path")
        path = (self.root / storage_key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("storage_key escapes file store root")
        return path

    def put(
        self,
        data: bytes | bytearray | BinaryIO,
        *,
        filename: str,
        workspace_id: UUID | None = None,
        mime_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> FileRef:
        safe_name = Path(filename).name
        if not safe_name.strip() or safe_name in {".", ".."}:
            raise ValueError("filename cannot be empty")

        if isinstance(data, (bytes, bytearray)):
            payload = bytes(data)
        else:
            payload = data.read()
            if not isinstance(payload, bytes):
                raise TypeError("file stream must return bytes")

        file_id = uuid4()
        workspace_prefix = str(workspace_id) if workspace_id else "unscoped"
        storage_key = f"{workspace_prefix}/{file_id}{Path(safe_name).suffix}"
        path = self._safe_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

        return FileRef(
            file_id=file_id,
            workspace_id=workspace_id,
            filename=safe_name,
            storage_key=storage_key,
            mime_type=mime_type,
            size_bytes=len(payload),
            metadata=dict(metadata or {}),
        )

    def get(self, file: FileRef) -> bytes:
        path = self._safe_path(file.storage_key)
        if not path.is_file():
            raise FileNotFoundError(str(file.file_id))
        return path.read_bytes()

    def exists(self, file: FileRef) -> bool:
        return self._safe_path(file.storage_key).is_file()


class FileRegistry:
    """In-memory metadata registry for workspace file references."""

    def __init__(self) -> None:
        self._files: dict[UUID, FileRef] = {}

    def register(self, file: FileRef) -> FileRef:
        self._files[file.file_id] = file
        return file

    def get(self, file_id: UUID, *, workspace_id: UUID | None = None) -> FileRef:
        try:
            file = self._files[file_id]
        except KeyError as exc:
            raise FileNotFoundError(f"Unknown file: {file_id}") from exc
        if workspace_id is not None and file.workspace_id != workspace_id:
            raise FileNotFoundError(f"File {file_id} is not in workspace {workspace_id}")
        return file

    def list(self, *, workspace_id: UUID | None = None) -> tuple[FileRef, ...]:
        files = self._files.values()
        if workspace_id is not None:
            files = (file for file in files if file.workspace_id == workspace_id)
        return tuple(files)

    def remove(self, file_id: UUID, *, workspace_id: UUID | None = None) -> FileRef:
        file = self.get(file_id, workspace_id=workspace_id)
        del self._files[file_id]
        return file
