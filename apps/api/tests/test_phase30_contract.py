from nexus.core.autonomy import AutonomyController, AutonomyDecision, VerificationSignal
from nexus.core.autonomy_policy import default_autonomy_policy
from nexus.core.agent_state import AgentState
from nexus.core.self_correction import SelfCorrectionPlanner


def test_phase30_end_to_end_contract():
    policy = default_autonomy_policy()
    assert policy.can("revise")
    state = AgentState("produce verified answer")
    controller = AutonomyController()
    state.advance("verification")
    signal = VerificationSignal(True, 0.95, evidence=("unit-test",))
    decision = controller.decide(signal, controller_state := __import__("nexus.core.autonomy", fromlist=["AutonomyState"]).AutonomyState())
    assert decision is AutonomyDecision.COMPLETE
    plan = SelfCorrectionPlanner().plan(["example"], available_actions=["revise_output"])
    assert plan.actions
    assert state.checkpoints == []
