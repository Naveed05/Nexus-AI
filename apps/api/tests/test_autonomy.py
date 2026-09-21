import pytest

from nexus.core.autonomy import (
    AutonomyController, AutonomyDecision, AutonomyPolicy, AutonomyState, VerificationSignal,
)


def test_high_confidence_verified_result_completes():
    controller = AutonomyController()
    state = AutonomyState()
    decision = controller.decide(VerificationSignal(True, 0.95, evidence=("test-pass",)), state)
    assert decision is AutonomyDecision.COMPLETE


def test_failed_verification_triggers_bounded_revision():
    controller = AutonomyController(AutonomyPolicy(max_revisions=2))
    outputs = []
    def execute(revision):
        outputs.append(revision)
        return revision
    def verify(result, revision):
        return VerificationSignal(result == 2, 0.9 if result == 2 else 0.7,
                                  issues=() if result == 2 else ("needs-fix",),
                                  evidence=("final-test",) if result == 2 else ("test-fail",))
    result, state, decision = controller.run_loop(execute, verify)
    assert result == 2
    assert state.revisions == 2
    assert decision is AutonomyDecision.COMPLETE
    assert outputs == [0, 1, 2]


def test_low_confidence_escalates_without_unbounded_loop():
    controller = AutonomyController(AutonomyPolicy(max_revisions=5))
    state = AutonomyState()
    decision = controller.decide(VerificationSignal(False, 0.2), state)
    assert decision is AutonomyDecision.ESCALATE


def test_revision_limit_escalates():
    controller = AutonomyController(AutonomyPolicy(max_revisions=1))
    state = AutonomyState(revisions=1)
    decision = controller.decide(VerificationSignal(False, 0.8), state)
    assert decision is AutonomyDecision.ESCALATE
