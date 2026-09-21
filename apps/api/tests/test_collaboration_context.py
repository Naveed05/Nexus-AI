import pytest
from nexus.core.collaboration_context import SharedAgentContext

def test_shared_context_preserves_provenance_and_versions():
    context = SharedAgentContext()
    first = context.put("evidence", ["source-a"], "researcher")
    second = context.put("evidence", ["source-a", "source-b"], "researcher", expected_version=1)
    assert first.version == 1 and second.version == 2
    assert context.get("evidence").source_agent == "researcher"

def test_shared_context_rejects_stale_writes():
    context = SharedAgentContext()
    context.put("answer", "draft", "writer")
    with pytest.raises(ValueError, match="version conflict"):
        context.put("answer", "stale", "analyst", expected_version=0)

def test_handoff_contains_requested_context_only():
    context = SharedAgentContext()
    context.put("evidence", "primary", "researcher")
    context.put("draft", "text", "writer")
    handoff = context.handoff("researcher", "writer", "synthesize", ("evidence",))
    assert handoff.to_agent == "writer"
    assert [entry.key for entry in handoff.context] == ["evidence"]
