from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from nexus.core.datasets import DatasetRegistry
from nexus.core.documents import DocumentWorkspace
from nexus.core.files import FileRegistry
from nexus.core.workspaces import WorkspaceRegistry


@dataclass(frozen=True)
class WorkspaceIntelligence:
    """Deterministic, restart-safe intelligence about one workspace."""

    workspace_id: UUID
    owner_id: str | None
    name: str
    resource_counts: dict[str, int]
    resources: dict[str, list[dict[str, Any]]]
    readiness: dict[str, bool]
    recommendations: tuple[str, ...]
    context: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": str(self.workspace_id),
            "owner_id": self.owner_id,
            "name": self.name,
            "resource_counts": self.resource_counts,
            "resources": self.resources,
            "readiness": self.readiness,
            "recommendations": list(self.recommendations),
            "context": self.context,
        }


class WorkspaceIntelligenceService:
    """Build a bounded context pack without executing tools or model calls."""

    def __init__(
        self,
        workspaces: WorkspaceRegistry,
        files: FileRegistry,
        datasets: DatasetRegistry,
        documents: DocumentWorkspace,
    ) -> None:
        self.workspaces = workspaces
        self.files = files
        self.datasets = datasets
        self.documents = documents

    def inspect(self, workspace_id: UUID, *, max_context_chars: int = 8000) -> WorkspaceIntelligence:
        workspace = self.workspaces.get(workspace_id)
        context = self.workspaces.context(workspace_id)
        file_items = [
            {
                "file_id": str(item.file_id),
                "filename": item.filename,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "dataset_id": item.metadata.get("dataset_id"),
            }
            for item in self.files.list(workspace_id=workspace_id)
        ]
        dataset_items = []
        for dataset_id in context.dataset_ids:
            try:
                dataset = self.datasets.get(dataset_id)
            except KeyError:
                continue
            dataset_items.append({
                "dataset_id": str(dataset.dataset_id),
                "filename": dataset.filename,
                "format": dataset.file_format,
                "size_bytes": dataset.size_bytes,
                "artifact_id": str(dataset.artifact_id) if dataset.artifact_id else None,
            })
        document_items = []
        for document_id in context.document_ids:
            try:
                document = self.documents.get(document_id)
            except Exception:
                continue
            document_items.append({
                "document_id": str(document.document_id),
                "filename": document.filename,
                "format": document.file_format,
                "size_bytes": document.size_bytes,
                "chunk_count": len(self.documents.get_chunks(document.document_id)),
            })

        readiness = {
            "has_resources": bool(file_items or dataset_items or document_items),
            "has_tabular_data": bool(dataset_items),
            "has_searchable_knowledge": bool(document_items),
            "has_agent_context": bool(context.file_ids or context.dataset_ids or context.document_ids),
        }
        recommendations: list[str] = []
        if not file_items:
            recommendations.append("Upload a reference file or dataset to give this workspace durable source material.")
        if file_items and not dataset_items:
            recommendations.append("Add a CSV, Parquet, or JSON dataset when the work requires structured analysis.")
        if file_items and not document_items:
            recommendations.append("Add a text, Markdown, PDF, or DOCX document when the work needs grounded knowledge retrieval.")
        if document_items:
            recommendations.append("Use workspace search to retrieve cited evidence before asking the agent to synthesize factual answers.")
        if dataset_items:
            recommendations.append("Run a data-science profile before modeling so missing values, duplicates, schema, and target suitability are explicit.")
        if not recommendations:
            recommendations.append("Workspace context is ready for agent execution.")

        lines = [
            f"workspace_id: {workspace.workspace_id}",
            f"workspace_name: {workspace.name}",
            f"owner_id: {workspace.owner_id or 'unknown'}",
            f"files: {len(file_items)}",
            f"datasets: {len(dataset_items)}",
            f"documents: {len(document_items)}",
        ]
        for item in file_items:
            lines.append(f"file: {item['filename']} ({item['size_bytes']} bytes)")
        for item in dataset_items:
            lines.append(f"dataset: {item['filename']} [{item['format']}]")
        for item in document_items:
            lines.append(f"document: {item['filename']} [{item['chunk_count']} chunks]")
        packed = "\n".join(lines)
        if max_context_chars < 1:
            raise ValueError("max_context_chars must be positive")
        context_text = packed[:max_context_chars]

        return WorkspaceIntelligence(
            workspace_id=workspace_id,
            owner_id=workspace.owner_id,
            name=workspace.name,
            resource_counts={
                "files": len(file_items),
                "datasets": len(dataset_items),
                "documents": len(document_items),
                "artifacts": len(context.artifact_ids),
            },
            resources={"files": file_items, "datasets": dataset_items, "documents": document_items},
            readiness=readiness,
            recommendations=tuple(recommendations),
            context=context_text,
        )

    def context(self, workspace_id: UUID, *, max_chars: int = 8000) -> str:
        return self.inspect(workspace_id, max_context_chars=max_chars).context
