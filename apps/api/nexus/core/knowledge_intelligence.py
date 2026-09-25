from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from uuid import UUID

from nexus.core.knowledge import KnowledgeEngine, KnowledgeSearch


@dataclass(frozen=True)
class KnowledgeIntelligence:
    query: str
    workspace_id: UUID
    result_count: int
    citations: tuple[str, ...]
    confidence: float
    context: str
    results: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "workspace_id": str(self.workspace_id),
            "result_count": self.result_count,
            "citations": list(self.citations),
            "confidence": self.confidence,
            "context": self.context,
            "results": list(self.results),
        }


class KnowledgeIntelligenceService:
    """Bounded RAG preparation: normalize queries, retrieve evidence, and build citations."""

    def __init__(self, engine: KnowledgeEngine) -> None:
        self.engine = engine

    @staticmethod
    def normalize_query(query: str) -> str:
        value = re.sub(r"\s+", " ", query).strip()
        if not value:
            raise ValueError("query cannot be empty")
        if len(value) > 2000:
            raise ValueError("query cannot exceed 2000 characters")
        return value

    def search(
        self,
        workspace_id: UUID,
        query: str,
        *,
        top_k: int = 8,
        max_context_chars: int = 8000,
    ) -> KnowledgeIntelligence:
        if top_k < 1 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")
        if max_context_chars < 1 or max_context_chars > 20000:
            raise ValueError("max_context_chars must be between 1 and 20000")
        normalized = self.normalize_query(query)
        search: KnowledgeSearch = self.engine.search(normalized, workspace_id=workspace_id, top_k=top_k)
        results = []
        citations: list[str] = []
        for result in search.results:
            citation = result.citation
            if citation not in citations:
                citations.append(citation)
            results.append({
                "chunk_id": str(result.chunk.chunk_id),
                "document_id": str(result.chunk.document_id),
                "text": result.chunk.text,
                "score": round(float(result.score), 6),
                "vector_score": round(float(result.vector_score), 6),
                "lexical_score": round(float(result.lexical_score), 6),
                "citation": citation,
                "metadata": result.chunk.metadata,
            })
        context = self.engine.context_builder.build(list(search.results), max_chars=max_context_chars)
        confidence = 0.0
        if search.results:
            confidence = min(1.0, max(0.0, sum(max(item.score, 0.0) for item in search.results[:3]) / min(3, len(search.results))))
        return KnowledgeIntelligence(
            query=normalized,
            workspace_id=workspace_id,
            result_count=len(results),
            citations=tuple(citations),
            confidence=round(confidence, 4),
            context=context,
            results=tuple(results),
        )

    def rebuild_workspace(self, workspace_id: UUID) -> int:
        total = 0
        for document_id, document in self.engine.documents.documents.items():
            if document.workspace_id == workspace_id:
                total += self.engine.retrieval.index_document(document_id)
        return total

    def health(self, workspace_id: UUID) -> dict[str, Any]:
        documents = [
            document for document in self.engine.documents.documents.values()
            if document.workspace_id == workspace_id
        ]
        indexed = 0
        for document in documents:
            indexed += len(self.engine.documents.get_chunks(document.document_id))
        return {
            "workspace_id": str(workspace_id),
            "documents": len(documents),
            "chunks": indexed,
            "embedding_provider": getattr(self.engine.retrieval.embeddings, "signature", "unknown"),
            "indexed": bool(indexed),
        }
