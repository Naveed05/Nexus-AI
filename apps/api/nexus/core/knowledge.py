from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import UUID

from .documents import DocumentWorkspace
from .retrieval import KnowledgeContextBuilder, JsonVectorStore, RetrievalEngine, RetrievalResult


@dataclass(frozen=True)
class KnowledgeSearch:
    query: str
    workspace_id: UUID | None
    results: tuple[RetrievalResult, ...]
    context: str

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "results": [
                {
                    "chunk_id": str(result.chunk.chunk_id),
                    "document_id": str(result.chunk.document_id),
                    "text": result.chunk.text,
                    "score": result.score,
                    "vector_score": result.vector_score,
                    "lexical_score": result.lexical_score,
                    "citation": result.citation,
                    "metadata": result.chunk.metadata,
                }
                for result in self.results
            ],
            "context": self.context,
        }


class KnowledgeEngine:
    """Application-level knowledge service for ingestion, indexing and grounded search."""

    def __init__(self, documents: DocumentWorkspace, index_path: str | Path) -> None:
        self.documents = documents
        self.retrieval = RetrievalEngine(documents, store=JsonVectorStore(index_path))
        self.context_builder = KnowledgeContextBuilder()

    def ingest(self, data: bytes, *, filename: str, workspace_id: UUID | None = None, metadata: dict[str, str] | None = None) -> tuple[object, int]:
        document = self.documents.register(data, filename=filename, workspace_id=workspace_id, metadata=metadata)
        return document, self.retrieval.index_document(document.document_id)

    def search(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5, document_id: UUID | None = None) -> KnowledgeSearch:
        results = self.retrieval.search(query, workspace_id=workspace_id, top_k=top_k, document_id=document_id)
        return KnowledgeSearch(query=query, workspace_id=workspace_id, results=tuple(results), context=self.context_builder.build(results))


_active_knowledge_engine: KnowledgeEngine | None = None
_active_workspace_id: ContextVar[UUID | None] = ContextVar("nexus_knowledge_workspace_id", default=None)


def configure_knowledge_engine(engine: KnowledgeEngine | None) -> None:
    global _active_knowledge_engine
    _active_knowledge_engine = engine


def set_knowledge_workspace(workspace_id: UUID | None):
    return _active_workspace_id.set(workspace_id)


def reset_knowledge_workspace(token) -> None:
    _active_workspace_id.reset(token)


def search_knowledge(query: str, top_k: int = 5, document_id: str | None = None) -> dict:
    if _active_knowledge_engine is None:
        raise RuntimeError("Knowledge engine is not configured")
    try:
        parsed_document_id = UUID(document_id) if document_id else None
    except ValueError as exc:
        raise ValueError(f"Invalid document_id: {document_id}") from exc
    return _active_knowledge_engine.search(
        query,
        workspace_id=_active_workspace_id.get(),
        top_k=max(1, min(int(top_k), 20)),
        document_id=parsed_document_id,
    ).as_dict()


class KnowledgeTool:
    """Tool-shaped adapter used by agents without exposing internal retrieval state."""

    name = "search_knowledge"
    description = "Search workspace documents using hybrid retrieval and return grounded evidence with citations."

    def __init__(self, engine: KnowledgeEngine, workspace_id_provider: Callable[[], UUID | None] | None = None) -> None:
        self.engine = engine
        self.workspace_id_provider = workspace_id_provider or (lambda: None)

    def execute(self, query: str, *, top_k: int = 5, document_id: str | None = None) -> dict:
        parsed_document_id = UUID(document_id) if document_id else None
        return self.engine.search(query, workspace_id=self.workspace_id_provider(), top_k=top_k, document_id=parsed_document_id).as_dict()
