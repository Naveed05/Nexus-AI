from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .knowledge import KnowledgeEngine


@dataclass(frozen=True)
class EvidencePack:
    query: str
    workspace_id: UUID | None
    results: tuple[dict[str, Any], ...]
    context: str
    citation_count: int
    grounding_ready: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "results": list(self.results),
            "context": self.context,
            "citation_count": self.citation_count,
            "grounding_ready": self.grounding_ready,
        }


class RAGIntelligence:
    """Evidence-first retrieval layer with deterministic citation and grounding checks."""

    def __init__(self, knowledge: KnowledgeEngine) -> None:
        self.knowledge = knowledge

    def retrieve(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5, document_id: UUID | None = None) -> EvidencePack:
        if not query.strip():
            raise ValueError("query cannot be empty")
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        result = self.knowledge.search(query.strip(), workspace_id=workspace_id, top_k=top_k, document_id=document_id)
        evidence = tuple({
            "rank": index,
            "chunk_id": str(item.chunk.chunk_id),
            "document_id": str(item.chunk.document_id),
            "citation": item.citation,
            "text": item.chunk.text,
            "score": round(item.score, 6),
            "vector_score": round(item.vector_score, 6),
            "lexical_score": round(item.lexical_score, 6),
            "metadata": dict(item.chunk.metadata),
        } for index, item in enumerate(result.results, start=1))
        grounding_ready = bool(evidence) and all(item["citation"] and item["text"] for item in evidence)
        return EvidencePack(
            query=result.query,
            workspace_id=result.workspace_id,
            results=evidence,
            context=result.context,
            citation_count=len({item["citation"] for item in evidence}),
            grounding_ready=grounding_ready,
        )

    def answer_context(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5) -> dict[str, Any]:
        pack = self.retrieve(query, workspace_id=workspace_id, top_k=top_k)
        return {
            **pack.as_dict(),
            "instructions": "Use only the supplied evidence for factual claims; preserve citations and state when evidence is insufficient.",
        }
