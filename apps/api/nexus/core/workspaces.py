from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import UUID, uuid4


class WorkspaceNotFoundError(KeyError):
    """Raised when a workspace reference cannot be resolved."""


@dataclass(frozen=True)
class WorkspaceRef:
    """Stable metadata reference for a NEXUS workspace."""

    workspace_id: UUID = field(default_factory=uuid4)
    name: str = "Workspace"
    owner_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("workspace name cannot be empty")
        if self.owner_id is not None and not self.owner_id.strip():
            raise ValueError("owner_id cannot be empty")


@dataclass
class WorkspaceContext:
    """Durable resource references available to an agent inside a workspace."""

    workspace: WorkspaceRef
    file_ids: list[UUID] = field(default_factory=list)
    dataset_ids: list[UUID] = field(default_factory=list)
    artifact_ids: list[UUID] = field(default_factory=list)
    document_ids: list[UUID] = field(default_factory=list)

    def add_file(self, file_id: UUID) -> None:
        if file_id not in self.file_ids:
            self.file_ids.append(file_id)

    def remove_file(self, file_id: UUID) -> None:
        if file_id in self.file_ids:
            self.file_ids.remove(file_id)

    def add_dataset(self, dataset_id: UUID) -> None:
        if dataset_id not in self.dataset_ids:
            self.dataset_ids.append(dataset_id)

    def remove_dataset(self, dataset_id: UUID) -> None:
        if dataset_id in self.dataset_ids:
            self.dataset_ids.remove(dataset_id)

    def add_artifact(self, artifact_id: UUID) -> None:
        if artifact_id not in self.artifact_ids:
            self.artifact_ids.append(artifact_id)

    def remove_artifact(self, artifact_id: UUID) -> None:
        if artifact_id in self.artifact_ids:
            self.artifact_ids.remove(artifact_id)

    def add_document(self, document_id: UUID) -> None:
        if document_id not in self.document_ids:
            self.document_ids.append(document_id)

    def remove_document(self, document_id: UUID) -> None:
        if document_id in self.document_ids:
            self.document_ids.remove(document_id)

    def as_text(self) -> str:
        parts = [f"workspace_id: {self.workspace.workspace_id}"]
        if self.file_ids:
            parts.append("file_ids: " + ", ".join(str(value) for value in self.file_ids))
        if self.dataset_ids:
            parts.append("dataset_ids: " + ", ".join(str(value) for value in self.dataset_ids))
        if self.artifact_ids:
            parts.append("artifact_ids: " + ", ".join(str(value) for value in self.artifact_ids))
        if self.document_ids:
            parts.append("document_ids: " + ", ".join(str(value) for value in self.document_ids))
        return "\n".join(parts)


class WorkspaceRegistry:
    """Workspace metadata and resource relationships with optional SQLite durability."""

    def __init__(self, storage_path: str | None = None) -> None:
        self._storage_path = storage_path
        self._lock = RLock()
        self._workspaces: dict[UUID, WorkspaceRef] = {}
        self._contexts: dict[UUID, WorkspaceContext] = {}
        self._connection: sqlite3.Connection | None = None
        if storage_path is not None:
            path = os.path.abspath(storage_path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self._connection = sqlite3.connect(path, check_same_thread=False)
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner_id TEXT,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS workspace_resources (
                    workspace_id TEXT PRIMARY KEY,
                    file_ids TEXT NOT NULL,
                    dataset_ids TEXT NOT NULL,
                    artifact_ids TEXT NOT NULL,
                    document_ids TEXT NOT NULL
                )"""
            )
            self._connection.commit()
            self._load()

    def _load(self) -> None:
        assert self._connection is not None
        for row in self._connection.execute("SELECT * FROM workspaces ORDER BY created_at"):
            workspace = WorkspaceRef(
                workspace_id=UUID(row[0]),
                name=row[1],
                owner_id=row[2],
                metadata=json.loads(row[3] or "{}"),
                created_at=datetime.fromisoformat(row[4]),
            )
            self._workspaces[workspace.workspace_id] = workspace
            resources = self._connection.execute(
                "SELECT file_ids,dataset_ids,artifact_ids,document_ids FROM workspace_resources WHERE workspace_id=?",
                (str(workspace.workspace_id),),
            ).fetchone()
            self._contexts[workspace.workspace_id] = WorkspaceContext(
                workspace=workspace,
                file_ids=[UUID(value) for value in json.loads(resources[0])] if resources else [],
                dataset_ids=[UUID(value) for value in json.loads(resources[1])] if resources else [],
                artifact_ids=[UUID(value) for value in json.loads(resources[2])] if resources else [],
                document_ids=[UUID(value) for value in json.loads(resources[3])] if resources else [],
            )

    def _persist_workspace(self, workspace: WorkspaceRef) -> None:
        if self._connection is None:
            return
        self._connection.execute(
            "INSERT OR REPLACE INTO workspaces VALUES (?,?,?,?,?)",
            (str(workspace.workspace_id), workspace.name, workspace.owner_id, json.dumps(workspace.metadata), workspace.created_at.isoformat()),
        )
        self._connection.commit()

    def _persist_context(self, context: WorkspaceContext) -> None:
        if self._connection is None:
            return
        self._connection.execute(
            "INSERT OR REPLACE INTO workspace_resources VALUES (?,?,?,?,?)",
            (
                str(context.workspace.workspace_id),
                json.dumps([str(v) for v in context.file_ids]),
                json.dumps([str(v) for v in context.dataset_ids]),
                json.dumps([str(v) for v in context.artifact_ids]),
                json.dumps([str(v) for v in context.document_ids]),
            ),
        )
        self._connection.commit()

    def create(self, *, name: str, owner_id: str | None = None, metadata: dict[str, Any] | None = None) -> WorkspaceRef:
        with self._lock:
            workspace = WorkspaceRef(name=name, owner_id=owner_id, metadata=dict(metadata or {}))
            self._workspaces[workspace.workspace_id] = workspace
            context = WorkspaceContext(workspace=workspace)
            self._contexts[workspace.workspace_id] = context
            self._persist_workspace(workspace)
            self._persist_context(context)
            return workspace

    def get(self, workspace_id: UUID) -> WorkspaceRef:
        with self._lock:
            try:
                return self._workspaces[workspace_id]
            except KeyError as exc:
                raise WorkspaceNotFoundError(f"Unknown workspace: {workspace_id}") from exc

    def context(self, workspace_id: UUID) -> WorkspaceContext:
        with self._lock:
            self.get(workspace_id)
            return self._contexts[workspace_id]

    def save_context(self, workspace_id: UUID) -> WorkspaceContext:
        with self._lock:
            context = self.context(workspace_id)
            self._persist_context(context)
            return context

    def list(self) -> tuple[WorkspaceRef, ...]:
        with self._lock:
            return tuple(self._workspaces.values())

    def remove(self, workspace_id: UUID) -> WorkspaceRef:
        with self._lock:
            workspace = self.get(workspace_id)
            if self._connection is not None:
                self._connection.execute("DELETE FROM workspace_resources WHERE workspace_id=?", (str(workspace_id),))
                self._connection.execute("DELETE FROM workspaces WHERE workspace_id=?", (str(workspace_id),))
                self._connection.commit()
            del self._workspaces[workspace_id]
            self._contexts.pop(workspace_id, None)
            return workspace


workspace_registry = WorkspaceRegistry(os.getenv("NEXUS_WORKSPACE_STORAGE_PATH", ".nexus/workspaces.sqlite3"))
