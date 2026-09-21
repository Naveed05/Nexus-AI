import pytest
from nexus.core.collaboration_conflicts import AgentProposal, ConflictResolution, ConflictResolver

def test_evidence_backed_proposal_wins_with_margin():
    result = ConflictResolver().resolve((AgentProposal("researcher","A",("source",),0.9), AgentProposal("analyst","B",(),0.7)))
    assert result.resolution is ConflictResolution.ACCEPT and result.selected_agent == "researcher"

def test_agreeing_proposals_merge():
    result = ConflictResolver().resolve((AgentProposal("a","same",("s1",),0.8), AgentProposal("b","same",("s2",),0.7)))
    assert result.resolution is ConflictResolution.MERGE

def test_close_conflict_escalates():
    result = ConflictResolver().resolve((AgentProposal("a","one",("s1",),0.8), AgentProposal("b","two",("s2",),0.75)))
    assert result.resolution is ConflictResolution.ESCALATE

def test_invalid_confidence_rejected():
    with pytest.raises(ValueError): AgentProposal("a","claim",confidence=2)
