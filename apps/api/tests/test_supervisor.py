from nexus.core.collaboration_conflicts import AgentProposal, ConflictResolution
from nexus.core.multi_agent import DelegationRequest
from nexus.core.supervisor import AgentSupervisor

def test_supervisor_builds_bounded_plan():
    result = AgentSupervisor(max_workstreams=2).build_plan("verified brief", (
        DelegationRequest("collect evidence","research","supervisor"),
        DelegationRequest("verify findings","verification","supervisor"),
    ))
    assert len(result.plan.workstreams) == 2
    assert result.approval_required is True

def test_supervisor_keeps_conflict_resolution_policy_bounded():
    result = AgentSupervisor().resolve((AgentProposal("researcher","claim",("source",),0.9), AgentProposal("analyst","other",(),0.7)))
    assert result.resolution is ConflictResolution.ACCEPT
