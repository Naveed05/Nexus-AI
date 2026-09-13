from uuid import uuid4

import nexus.core.research as research_module
from nexus.core.research import ResearchEngine, ResearchSource, synthesize_evidence


def test_build_queries_is_bounded_and_deduplicated() -> None:
    queries = ResearchEngine(max_queries=3).build_queries("AI safety and agent verification")
    assert queries[0] == "AI safety and agent verification"
    assert len(queries) == len(set(queries))
    assert len(queries) >= 3


def test_research_plan_assigns_query_roles() -> None:
    plan = ResearchEngine.plan_queries("AI safety and agent verification", max_queries=4)
    assert plan.queries[0] == "AI safety and agent verification"
    assert plan.query_roles[0] == "primary_question"
    assert "supporting_evidence" in plan.query_roles
    assert "limitations" in plan.query_roles
    assert len(plan.queries) == len(plan.query_roles)


def test_research_deduplicates_evidence_and_preserves_query(monkeypatch) -> None:
    document_id = uuid4()
    chunk_id = uuid4()
    calls = []

    def fake_search(query: str, top_k: int = 5):
        calls.append((query, top_k))
        return {
            "results": [
                {
                    "document_id": str(document_id),
                    "chunk_id": str(chunk_id),
                    "citation": "notes.md — chunk 1",
                    "text": "Verified evidence.",
                    "score": 0.9,
                }
            ]
        }

    monkeypatch.setattr(research_module, "search_knowledge", fake_search)
    result = ResearchEngine(max_queries=2, results_per_query=4).research(
        "AI safety", workspace_id=uuid4()
    )

    assert len(calls) == 2
    assert all(top_k == 4 for _, top_k in calls)
    assert result.evidence_count == 1
    assert result.sources[0].citation == "notes.md — chunk 1"
    assert result.sources[0].query == result.queries[0]


def test_synthesize_evidence_sorts_sources_and_preserves_citations() -> None:
    sources = (
        ResearchSource("b.md — chunk 2", "doc-b", "chunk-b", "Lower confidence", 0.4, "limitations"),
        ResearchSource("a.md — chunk 1", "doc-a", "chunk-a", "Strong evidence", 0.9, "primary"),
        ResearchSource("a.md — chunk 3", "doc-a", "chunk-c", "Supporting evidence", 0.7, "evidence"),
    )
    synthesis = synthesize_evidence("Research question", sources)
    assert synthesis.source_count == 3
    assert synthesis.document_count == 2
    assert synthesis.query_count == 3
    assert 0.0 < synthesis.evidence_quality_score <= 1.0
    assert synthesis.evidence_blocks[0].startswith("[Source: a.md — chunk 1]")
    assert "Strong evidence" in synthesis.context
    assert "Query: limitations" in synthesis.context
    assert "evidence quality" in synthesis.context


def test_synthesize_evidence_empty_sources_has_zero_quality() -> None:
    synthesis = synthesize_evidence("Research question", ())
    assert synthesis.source_count == 0
    assert synthesis.document_count == 0
    assert synthesis.query_count == 0
    assert synthesis.evidence_quality_score == 0.0
    assert synthesis.context == "No supporting evidence was retrieved."


def test_research_rejects_empty_question() -> None:
    try:
        ResearchEngine().research("   ")
    except ValueError as exc:
        assert "cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
