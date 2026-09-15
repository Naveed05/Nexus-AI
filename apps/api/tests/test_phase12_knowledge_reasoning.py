from nexus.core.cross_memory_reasoner import CrossMemoryReasoner
from nexus.core.knowledge_synthesizer import KnowledgeSynthesizer


def test_knowledge_synthesis_is_deterministic_and_traceable():
    items = ("Python services use SQLite memory", "SQLite memory supports durable services", "Python services need verification")
    first = KnowledgeSynthesizer().synthesize(items, query="memory")
    second = KnowledgeSynthesizer().synthesize(items, query="memory")
    assert first == second
    assert first.evidence == items
    assert first.themes
    assert 0.0 <= first.confidence <= 1.0


def test_cross_memory_reasoning_preserves_sources_and_flags_gaps():
    result = CrossMemoryReasoner().reason(("The service uses SQLite", "The service uses SQLite for memory"), query="SQLite memory")
    assert result.supporting_items
    assert "SQLite" in result.conclusion
    assert result.confidence > 0.0


def test_empty_memory_is_safe():
    result = CrossMemoryReasoner().reason([], query="anything")
    assert result.confidence == 0.0
    assert "missing evidence" in result.gaps
