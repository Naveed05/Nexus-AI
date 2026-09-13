from uuid import uuid4

import nexus.core.research as research_module
from nexus.core.research import ResearchEngine


def test_build_queries_is_bounded_and_deduplicated() -> None:
    queries = ResearchEngine(max_queries=3).build_queries("AI safety and agent verification")
    assert queries[0] == "AI safety and agent verification"
    assert len(queries) == len(set(queries))
    assert len(queries) >= 3


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


def test_research_rejects_empty_question() -> None:
    try:
        ResearchEngine().research("   ")
    except ValueError as exc:
        assert "cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
