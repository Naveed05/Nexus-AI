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
        return {"citation": self.citation, "document_id": self.document_id, "chunk_id": self.chunk_id, "text": self.text, "score": self.score, "query": self.query}


@dataclass(frozen=True)
class ResearchPlan:
    question: str
    queries: tuple[str, ...]
    query_roles: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"question": self.question, "queries": list(self.queries), "query_roles": list(self.query_roles)}


@dataclass(frozen=True)
class ResearchSynthesis:
    question: str
    source_count: int
    document_count: int
    query_count: int
    query_coverage: tuple[tuple[str, int], ...]
    evidence_blocks: tuple[str, ...]
    evidence_quality_score: float
    provenance: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def confidence_band(self) -> str:
        if self.evidence_quality_score >= 0.75:
            return "high"
        if self.evidence_quality_score >= 0.45:
            return "moderate"
        if self.evidence_quality_score > 0.0:
            return "low"
        return "none"

    @property
    def context(self) -> str:
        if not self.evidence_blocks:
            return "No supporting evidence was retrieved."
        coverage = ", ".join(f"{query}: {count}" for query, count in self.query_coverage)
        header = f"RESEARCH EVIDENCE ({self.source_count} sources across {self.document_count} documents, {self.query_count} queries; evidence quality {self.evidence_quality_score:.2f}; confidence {self.confidence_band}; coverage {coverage}):"
        return header + "\n\n" + "\n\n".join(self.evidence_blocks)

    def as_dict(self) -> dict:
        return {"question": self.question, "source_count": self.source_count, "document_count": self.document_count, "query_count": self.query_count, "query_coverage": dict(self.query_coverage), "evidence_blocks": list(self.evidence_blocks), "evidence_quality_score": self.evidence_quality_score, "confidence_band": self.confidence_band, "provenance": {query: list(citations) for query, citations in self.provenance}, "context": self.context}

    def to_markdown(self) -> str:
        lines = [f"# Research Report: {self.question}", "", f"- Sources: {self.source_count}", f"- Documents: {self.document_count}", f"- Queries with evidence: {self.query_count}", f"- Evidence quality: {self.evidence_quality_score:.2f}", f"- Confidence band: {self.confidence_band}", "", "## Evidence", ""]
        if self.evidence_blocks:
            lines.extend(self.evidence_blocks)
        else:
            lines.append("No supporting evidence was retrieved.")
        lines.extend(["", "## Query Provenance", ""])
        for query, citations in self.provenance:
            lines.append(f"- **{query}**")
            for citation in citations:
                lines.append(f"  - {citation}")
        return "\n".join(lines)


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
        return {"question": self.question, "queries": list(self.queries), "evidence_count": self.evidence_count, "sources": [source.as_dict() for source in self.sources], "plan": (self.plan or ResearchPlan(self.question, self.queries, tuple())).as_dict(), "synthesis": self.synthesis.as_dict()}


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
            queries.extend(part.strip(" ,") for part in clean.split(" and ")[:2] if part.strip(" ,"))
        elif " vs " in lowered:
            queries.extend(part.strip(" ,") for part in clean.split(" vs ")[:2] if part.strip(" ,"))
        queries.extend((f"evidence for {clean}", f"limitations of {clean}"))
        return tuple(dict.fromkeys(queries))

    @staticmethod
    def plan_queries(question: str, max_queries: int = 4) -> ResearchPlan:
        clean = " ".join(question.split())
        if not clean:
            raise ValueError("Research question cannot be empty")
        limit = max(1, min(max_queries, 8))
        candidates = ResearchEngine.build_queries(clean)
        primary = candidates[0]
        evidence = next((q for q in candidates if q.startswith("evidence for ")), None)
        limitations = next((q for q in candidates if q.startswith("limitations of ")), None)
        subtopics = [q for q in candidates[1:] if q != evidence and q != limitations]
        ordered = [primary]
        for query in (evidence, limitations, *subtopics):
            if query is not None and query not in ordered:
                ordered.append(query)
        queries = tuple(ordered[:limit])
        roles = ["primary_question" if q == primary else "supporting_evidence" if q == evidence else "limitations" if q == limitations else "subtopic" for q in queries]
        return ResearchPlan(clean, queries, tuple(roles))

    def research(self, question: str, *, workspace_id: UUID | None = None) -> ResearchResult:
        plan = self.plan_queries(question, self.max_queries)
        sources: list[ResearchSource] = []
        seen: set[tuple[str, str]] = set()
        token: Token | None = set_knowledge_workspace(workspace_id) if workspace_id is not None else None
        try:
            for query in plan.queries:
                result = search_knowledge(query, self.results_per_query)
                for item in result.get("results", []):
                    key = (str(item.get("document_id", "")), str(item.get("chunk_id", "")))
                    if key in seen:
                        continue
                    seen.add(key)
                    sources.append(ResearchSource(str(item.get("citation", "")), key[0], key[1], str(item.get("text", "")), float(item.get("score", 0.0)), query))
        finally:
            if token is not None:
                reset_knowledge_workspace(token)
        return ResearchResult(plan.question, plan.queries, tuple(sources), plan)


def _select_diverse_sources(sources: tuple[ResearchSource, ...], *, limit: int = 12, per_document: int = 3) -> list[ResearchSource]:
    selected: list[ResearchSource] = []
    document_counts: dict[str, int] = {}
    for source in sorted(sources, key=lambda source: source.score, reverse=True):
        count = document_counts.get(source.document_id, 0)
        if count >= per_document:
            continue
        selected.append(source)
        document_counts[source.document_id] = count + 1
        if len(selected) >= limit:
            break
    return selected


def synthesize_evidence(question: str, sources: tuple[ResearchSource, ...]) -> ResearchSynthesis:
    clean = " ".join(question.split())
    if not clean:
        raise ValueError("Research question cannot be empty")
    selected = [source for source in _select_diverse_sources(sources) if source.text.strip()]
    blocks = tuple(f"[Source: {source.citation}]\nQuery: {source.query}\n{source.text[:2000]}" for source in selected)
    if selected:
        average_score = sum(max(0.0, min(1.0, source.score)) for source in selected) / len(selected)
        document_diversity = min(1.0, len({source.document_id for source in selected}) / 3.0)
        query_diversity = min(1.0, len({source.query for source in selected}) / 3.0)
        evidence_quality_score = round(0.6 * average_score + 0.2 * document_diversity + 0.2 * query_diversity, 4)
    else:
        evidence_quality_score = 0.0
    queries = {source.query for source in selected}
    coverage = tuple(sorted(((query, sum(1 for source in selected if source.query == query)) for query in queries), key=lambda item: item[0]))
    provenance = tuple(sorted((query, tuple(sorted({source.citation for source in selected if source.query == query}))) for query in queries))
    return ResearchSynthesis(clean, len(selected), len({source.document_id for source in selected}), len(queries), coverage, blocks, evidence_quality_score, provenance)


def research_knowledge(question: str, max_queries: int = 4, results_per_query: int = 5) -> dict:
    return ResearchEngine(max_queries=max_queries, results_per_query=results_per_query).research(question).as_dict()
