from nexus.core.agent_state import AgentState


def test_agent_state_checkpoint_and_restore():
    state = AgentState("build verified artifact")
    state.advance("execution", artifact="draft")
    checkpoint = state.checkpoint()
    state.advance("verification", artifact="bad")
    state.restore(checkpoint)
    assert state.phase == "execution"
    assert state.step == 1
    assert state.context["artifact"] == "draft"


def test_checkpoint_cannot_cross_objectives():
    from nexus.core.agent_state import AgentCheckpoint
    from datetime import datetime, timezone
    from uuid import uuid4
    import pytest
    checkpoint = AgentCheckpoint(uuid4(), 1, "other", {}, datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        AgentState("current").restore(checkpoint)
