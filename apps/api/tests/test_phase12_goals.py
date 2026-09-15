from nexus.core.goal_manager import GoalManager
from nexus.core.long_horizon_planner import LongHorizonPlanner


def test_goal_manager_tracks_lifecycle_and_completion() -> None:
    manager = GoalManager()
    goal = manager.create("Ship the next NEXUS release", ["plan", "implement", "verify"])

    assert goal.status == "pending"
    assert goal.progress == 0.0

    manager.activate(goal)
    manager.update_progress(goal, 0.5)
    assert goal.status == "active"
    assert goal.progress == 0.5

    manager.update_progress(goal, 1.0)
    assert goal.status == "completed"
    assert goal.progress == 1.0


def test_long_horizon_planner_builds_ordered_dependencies() -> None:
    manager = GoalManager()
    goal = manager.create("Build a production AI platform", ["foundation", "intelligence", "hardening"])

    plan = LongHorizonPlanner().build(goal)

    assert plan.goal_id == str(goal.goal_id)
    assert [item.milestone_id for item in plan.milestones] == ["m1", "m2", "m3"]
    assert plan.milestones[0].depends_on == ()
    assert plan.milestones[1].depends_on == ("m1",)
    assert plan.milestones[2].depends_on == ("m2",)
    assert [item.horizon for item in plan.milestones] == [1, 2, 3]
