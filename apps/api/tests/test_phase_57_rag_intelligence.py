from pathlib import Path

from nexus.core.documents import DocumentWorkspace
from nexus.core.knowledge import KnowledgeEngine
from nexus.core.rag_intelligence import RAGIntelligence


def test_rag_returns_citation_bearing_grounded_evidence(tmp_path: Path) -> None:
    documents = DocumentWorkspace(tmp_path / "docs")
    engine = KnowledgeEngine(documents, tmp_path / "index.json")
    document, chunks = engine.ingest(b"NEXUS verifies evidence before delivery.\n\nWorkspace retrieval is scoped.", filename="guide.txt")
    assert chunks >= 1

    rag = RAGIntelligence(engine)
    pack = rag.retrieve("evidence delivery", workspace_id=document.workspace_id, top_k=3)

    assert pack.citation_count >= 1
    assert pack.grounding_ready is True
    assert pack.results[0]["citation"].startswith("guide.txt")
    assert pack.results[0]["text"]


def test_rag_rejects_invalid_bounds(tmp_path: Path) -> None:
    documents = DocumentWorkspace(tmp_path / "docs")
    engine = KnowledgeEngine(documents, tmp_path / "index.json")
    rag = RAGIntelligence(engine)

    try:
        rag.retrieve("hello", top_k=0)
    except ValueError as exc:
        assert "between 1 and 20" in str(exc)
    else:
        raise AssertionError("expected invalid top_k failure")
