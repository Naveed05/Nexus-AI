import pytest

from nexus.core.human_control import ControlRisk, HumanControlPolicy


def test_blocked_actions_cannot_proceed_even_with_approval():
    decision = HumanControlPolicy().evaluate("credential_exfiltration", approved=True)

    assert decision.risk is ControlRisk.BLOCKED
    assert not decision.allowed
    assert not decision.requires_approval


def test_high_risk_actions_require_explicit_approval():
    policy = HumanControlPolicy()

    pending = policy.evaluate("production_deploy")
    approved = policy.evaluate("production_deploy", approved=True)

    assert pending.risk is ControlRisk.HIGH
    assert not pending.allowed
    assert pending.requires_approval
    assert approved.allowed
    assert not approved.requires_approval


def test_medium_risk_actions_are_allowed_without_approval():
    decision = HumanControlPolicy().evaluate("file_write")

    assert decision.risk is ControlRisk.MEDIUM
    assert decision.allowed
    assert not decision.requires_approval


def test_unknown_actions_default_to_low_risk():
    decision = HumanControlPolicy().evaluate("read_metadata")

    assert decision.risk is ControlRisk.LOW
    assert decision.allowed


def test_action_names_are_normalized():
    decision = HumanControlPolicy().evaluate("  PRODUCTION_DEPLOY  ", approved=True)

    assert decision.action == "production_deploy"
    assert decision.allowed


def test_empty_action_is_rejected():
    with pytest.raises(ValueError, match="non-empty string"):
        HumanControlPolicy().evaluate("   ")


def test_overlapping_policy_tiers_are_rejected():
    with pytest.raises(ValueError, match="cannot also be risk-tiered"):
        HumanControlPolicy(
            blocked_actions=frozenset({"x"}),
            high_risk_actions=frozenset({"x"}),
        )
