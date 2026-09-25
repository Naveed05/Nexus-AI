from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from .memory import MemoryStore
from .workspaces import WorkspaceRegistry, WorkspaceNotFoundError


class WorkspaceIntelligence:
    """Builds bounded, deterministic workspace context without exposing raw secrets."""

    def __init__(self, registry: WorkspaceRegistry, memory: MemoryStore) -> None:
        self.registry = registry
        self.memory = memory

    def summary(self, workspace_id: UUID) -> dict[str, Any]:
        workspace = self.registry.get(workspace_id)
        context = self.registry.context(workspace_id)
        memories = self.memory.stats(workspace_id=workspace_id)
        return {
            "workspace": {
                "workspace_id": str(workspace.workspace_id),
                "name": workspace.name,
                "owner_id": workspace.owner_id,
                "metadata": dict(workspace.metadata),
                "created_at": workspace.created_at.isoformat(),
            },
            "resources": {
                "files": len(context.file_ids),
                "datasets": len(context.dataset_ids),
                "documents": len(context.document_ids),
                "artifacts": len(context.artifact_ids),
            },
            "memory": memories,
            "readiness": {
                "has_resources": any((context.file_ids, context.dataset_ids, context.document_ids)),
                "has_memory": memories["active"] > 0,
            },
        }

    def context_pack(self, workspace_id: UUID, *, objective: str | None = None, max_chars: int = 8000) -> dict[str, Any]:
        if max_chars < 500:
            raise ValueError("max_chars must be at least 500")
        workspace = self.registry.get(workspace_id)
        context = self.registry.context(workspace_id)
        parts = [f"WORKSPACE: {workspace.name}", f"workspace_id: {workspace.workspace_id}"]
        if workspace.metadata:
            parts.append("METADATA: " + ", ".join(f"{k}={v}" for k, v in sorted(workspace.metadata.items())))
        resources = [
            ("files", context.file_ids),
            ("datasets", context.dataset_ids),
            ("documents", context.document_ids),
            ("artifacts", context.artifact_ids),
        ]
        for label, ids in resources:
            if ids:
                parts.append(f"{label}: " + ", ".join(str(value) for value in ids))
        if objective:
            memory = self.memory.recall_context(objective, workspace_id=workspace_id, top_k=8, max_chars=max_chars // 2)
            if memory:
                parts.append(memory)
        rendered = "\n".join(parts)[:max_chars]
        return {
            "workspace_id": str(workspace_id),
            "objective": objective,
            "context": rendered,
            "truncated": len("\n".join(parts)) > max_chars,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def inventory(self, workspace_id: UUID) -> dict[str, list[str]]:
        context = self.registry.context(workspace_id)
        return {
            "file_ids": [str(v) for v in context.file_ids],
            "dataset_ids": [str(v) for v in context.dataset_ids],
            "document_ids": [str(v) for v in context.document_ids],
            "artifact_ids": [str(v) for v in context.artifact_ids],
        }

    def readiness(self, workspace_id: UUID) -> dict[str, Any]:
        summary = self.summary(workspace_id)
        resources = summary["resources"]
        checks = {
            "workspace_exists": True,
            "has_files": resources["files"] > 0,
            "has_datasets": resources["datasets"] > 0,
            "has_documents": resources["documents"] > 0,
            "has_memory": summary["memory"]["active"] > 0,
        }
        return {"workspace_id": str(workspace_id), "checks": checks, "ready": checks["has_files"] or checks["has_datasets"] or checks["has_documents"]}
