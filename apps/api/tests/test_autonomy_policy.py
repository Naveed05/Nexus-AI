from nexus.core.autonomy_policy import default_autonomy_policy


def test_autonomy_policy_preserves_human_control():
    policy = default_autonomy_policy()
    assert policy.can("plan")
    assert policy.can("revise")
    assert not policy.can("external_side_effect")
    assert policy.approval_required("external_side_effect")
    assert policy.approval_required("change_policy")
