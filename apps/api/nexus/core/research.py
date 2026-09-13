from __future__ import annotations

from contextvars import Token
from dataclasses import dataclass
from uuid import UUID

from .knowledge import reset_knowledge_workspace, search_knowledge, set_knowledge_workspace


@dataclass(frozen=True)
class ResearchSource:
    citation: str
    document_id: str
    chunk_id: str
    text: str
    score: float
    query: str

    def as_dict(self) -> dict:
        return {
            "citation": self.citation,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "score": self.score,
            "query": self.query,
        }


@dataclass(frozen=True)
class ResearchResult:
    question: str
    queries: tuple[str, ...]
    sources: tuple[ResearchSource, ...]

    @property
    def evidence_count(self) -> int:
        return len(self.sources)

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "queries": list(self.queries),
            "evidence_count": self.evidence_count,
            "sources": [source.as_dict() for source in self.sources],
        }


class ResearchEngine:
    """Runs bounded, evidence-first research over the configured knowledge workspace."""

    def __init__(self, *, max_queries: int = 4, results_per_query: int = 5) -> None:
        if max_queries <= 0:
            raise ValueError("max_queries must be greater than zero")
        if results_per_query <= 0:
            raise ValueError("results_per_query must be greater than zero")
        self.max_queries = min(max_queries, 8)
        self.results_per_query = min(results_per_query, 20)

    @staticmethod
    def build_queries(question: str) -> tuple[str, ...]:
        clean = " ".join(question.split())
        if not clean:
            raise ValueError("Research question cannot be empty")
        queries = [clean]
        lowered = clean.lower()
        if " and " in lowered:
            parts = [part.strip(" ,") for part in clean.split(" and ") if part.strip(" ,")]
            queries.extend(parts[:2])
        elif " vs " in lowered:
            parts = [part.strip(" ,") for part in clean.split(" vs ") if part.strip(" ,")]
            queries.extend(parts[:2])
        queries.append(f"evidence for {clean}")
        queries.append(f"limitations of {clean}")
        return tuple(dict.fromkeys(queries))

    def research(self, question: str, *, workspace_id: UUID | None = None) -> ResearchResult:
        queries = self.build_queries(question)[: self.max_queries]
        sources: list[ResearchSource] = []
        seen: set[tuple[str, str]] = set()
        token: Token | None = None
        if workspace_id is not None:
            token = set_knowledge_workspace(workspace_id)
        try:
            for query in queries:
                result = search_knowledge(query, self.results_per_query)
                for item in result.get("results", []):
                    key = (str(item.get("document_id", "")), str(item.get("chunk_id", "")))
                    if key in seen:
                        continue
                    seen.add(key)
                    sources.append(
                        ResearchSource(
                            citation=str(item.get("citation", "")),
                            document_id=key[0],
                            chunk_id=key[1],
                            text=str(item.get("text", "")),
                            score=float(item.get("score", 0.0)),
                            query=query,
                        )
                    )
        finally:
            if token is not None:
                reset_knowledge_workspace(token)
        return ResearchResult(question=" ".join(question.split()), queries=queries, sources=tuple(sources))


def research_knowledge(question: str, max_queries: int = 4, results_per_query: int = 5) -> dict:
    """Research a question across workspace knowledge using bounded query expansion."""
    return ResearchEngine(max_queries=max_queries, results_per_query=results_per_query).research(question).as_dict()
