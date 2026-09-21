from nexus.core.self_correction import SelfCorrectionPlanner


def test_correction_planner_maps_issues_to_available_actions():
    plan = SelfCorrectionPlanner().plan(
        ["missing citation", "wrong total"],
        available_actions=["revise_output"],
    )
    assert len(plan.actions) == 2
    assert plan.actions[0].action == "revise_output"
    assert "2" in plan.rationale


def test_empty_actions_do_not_invent_authority():
    plan = SelfCorrectionPlanner().plan(["unknown failure"], available_actions=[])
    assert plan.actions == ()
