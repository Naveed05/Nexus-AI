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
class ResearchPlan:
    question: str
    queries: tuple[str, ...]
    query_roles: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "queries": list(self.queries),
            "query_roles": list(self.query_roles),
        }


@dataclass(frozen=True)
class ResearchSynthesis:
    question: str
    source_count: int
    document_count: int
    query_count: int
    evidence_blocks: tuple[str, ...]
    evidence_quality_score: float

    @property
    def context(self) -> str:
        if not self.evidence_blocks:
            return "No supporting evidence was retrieved."
        header = (
            f"RESEARCH EVIDENCE ({self.source_count} sources across "
            f"{self.document_count} documents, {self.query_count} queries; "
            f"evidence quality {self.evidence_quality_score:.2f}):"
        )
        return header + "\n\n" + "\n\n".join(self.evidence_blocks)

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "source_count": self.source_count,
            "document_count": self.document_count,
            "query_count": self.query_count,
            "evidence_blocks": list(self.evidence_blocks),
            "evidence_quality_score": self.evidence_quality_score,
            "context": self.context,
        }


@dataclass(frozen=True)
class ResearchResult:
    question: str
    queries: tuple[str, ...]
    sources: tuple[ResearchSource, ...]
    plan: ResearchPlan | None = None

    @property
    def evidence_count(self) -> int:
        return len(self.sources)

    @property
    def synthesis(self) -> ResearchSynthesis:
        return synthesize_evidence(self.question, self.sources)

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "queries": list(self.queries),
            "evidence_count": self.evidence_count,
            "sources": [source.as_dict() for source in self.sources],
            "plan": (self.plan or ResearchPlan(self.question, self.queries, tuple())).as_dict(),
            "synthesis": self.synthesis.as_dict(),
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

    @staticmethod
    def plan_queries(question: str, max_queries: int = 4) -> ResearchPlan:
        clean = " ".join(question.split())
        if not clean:
            raise ValueError("Research question cannot be empty")
        limit = max(1, min(max_queries, 8))
        candidates = ResearchEngine.build_queries(clean)
        primary = candidates[0]
        evidence = next((query for query in candidates if query.startswith("evidence for ")), None)
        limitations = next((query for query in candidates if query.startswith("limitations of ")), None)
        subtopics = [
            query
            for query in candidates[1:]
            if query != evidence and query != limitations
        ]
        ordered = [primary]
        for query in (evidence, limitations, *subtopics):
            if query is not None and query not in ordered:
                ordered.append(query)
        queries = tuple(ordered[:limit])
        roles = []
        for query in queries:
            if query == primary:
                roles.append("primary_question")
            elif query == evidence:
                roles.append("supporting_evidence")
            elif query == limitations:
                roles.append("limitations")
            else:
                roles.append("subtopic")
        return ResearchPlan(clean, queries, tuple(roles))

    def research(self, question: str, *, workspace_id: UUID | None = None) -> ResearchResult:
        plan = self.plan_queries(question, self.max_queries)
        sources: list[ResearchSource] = []
        seen: set[tuple[str, str]] = set()
        token: Token | None = None
        if workspace_id is not None:
            token = set_knowledge_workspace(workspace_id)
        try:
            for query in plan.queries:
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
        return ResearchResult(question=plan.question, queries=plan.queries, sources=tuple(sources), plan=plan)


def synthesize_evidence(question: str, sources: tuple[ResearchSource, ...]) -> ResearchSynthesis:
    """Build bounded, citation-preserving synthesis context for a downstream agent."""
    clean = " ".join(question.split())
    if not clean:
        raise ValueError("Research question cannot be empty")
    ordered = sorted(sources, key=lambda source: source.score, reverse=True)
    selected = [source for source in ordered[:12] if source.text.strip()]
    blocks = tuple(
        f"[Source: {source.citation}]\nQuery: {source.query}\n{source.text[:2000]}"
        for source in selected
    )
    if selected:
        average_score = sum(max(0.0, min(1.0, source.score)) for source in selected) / len(selected)
        document_diversity = min(1.0, len({source.document_id for source in selected}) / 3.0)
        query_diversity = min(1.0, len({source.query for source in selected}) / 3.0)
        evidence_quality_score = round(
            0.6 * average_score + 0.2 * document_diversity + 0.2 * query_diversity,
            4,
        )
    else:
        evidence_quality_score = 0.0
    return ResearchSynthesis(
        question=clean,
        source_count=len(selected),
        document_count=len({source.document_id for source in selected}),
        query_count=len({source.query for source in selected}),
        evidence_blocks=blocks,
        evidence_quality_score=evidence_quality_score,
    )


def research_knowledge(question: str, max_queries: int = 4, results_per_query: int = 5) -> dict:
    """Research a question across workspace knowledge using bounded query expansion."""
    return ResearchEngine(max_queries=max_queries, results_per_query=results_per_query).research(question).as_dict()
