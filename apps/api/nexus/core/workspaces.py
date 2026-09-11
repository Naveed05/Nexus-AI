from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    """Resource references available to an agent inside a workspace."""

    workspace: WorkspaceRef
    file_ids: list[UUID] = field(default_factory=list)
    dataset_ids: list[UUID] = field(default_factory=list)
    artifact_ids: list[UUID] = field(default_factory=list)

    def add_file(self, file_id: UUID) -> None:
        if file_id not in self.file_ids:
            self.file_ids.append(file_id)

    def add_dataset(self, dataset_id: UUID) -> None:
        if dataset_id not in self.dataset_ids:
            self.dataset_ids.append(dataset_id)

    def add_artifact(self, artifact_id: UUID) -> None:
        if artifact_id not in self.artifact_ids:
            self.artifact_ids.append(artifact_id)


class WorkspaceRegistry:
    """In-memory workspace registry for the Phase 6A foundation."""

    def __init__(self) -> None:
        self._workspaces: dict[UUID, WorkspaceRef] = {}
        self._contexts: dict[UUID, WorkspaceContext] = {}

    def create(
        self,
        *,
        name: str,
        owner_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceRef:
        workspace = WorkspaceRef(
            name=name,
            owner_id=owner_id,
            metadata=dict(metadata or {}),
        )
        self._workspaces[workspace.workspace_id] = workspace
        self._contexts[workspace.workspace_id] = WorkspaceContext(workspace=workspace)
        return workspace

    def get(self, workspace_id: UUID) -> WorkspaceRef:
        try:
            return self._workspaces[workspace_id]
        except KeyError as exc:
            raise WorkspaceNotFoundError(f"Unknown workspace: {workspace_id}") from exc

    def context(self, workspace_id: UUID) -> WorkspaceContext:
        self.get(workspace_id)
        return self._contexts[workspace_id]

    def list(self) -> tuple[WorkspaceRef, ...]:
        return tuple(self._workspaces.values())

    def remove(self, workspace_id: UUID) -> WorkspaceRef:
        workspace = self.get(workspace_id)
        del self._workspaces[workspace_id]
        self._contexts.pop(workspace_id, None)
        return workspace
