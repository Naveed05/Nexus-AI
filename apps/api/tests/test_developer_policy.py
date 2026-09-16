import pytest

from nexus.core.developer_policy import DeveloperPolicy, PatchRisk


def test_small_patch_is_low_risk():
    decision = DeveloperPolicy().evaluate(("router.py",), additions=4, deletions=2)

    assert decision.risk is PatchRisk.LOW
    assert decision.allowed is True
    assert decision.requires_approval is False


def test_medium_patch_is_allowed_but_marked():
    decision = DeveloperPolicy().evaluate(
        ("router.py", "service.py", "tests/test_router.py"), additions=30, deletions=25
    )

    assert decision.risk is PatchRisk.MEDIUM
    assert decision.allowed is True
    assert any("moderate" in reason for reason in decision.reasons)


def test_large_patch_requires_explicit_approval():
    policy = DeveloperPolicy(max_files=8, max_changed_lines=400)

    pending = policy.evaluate(tuple(f"file{i}.py" for i in range(5)), additions=100, deletions=60)
    approved = policy.evaluate(
        tuple(f"file{i}.py" for i in range(5)), additions=100, deletions=60, approved=True
    )

    assert pending.risk is PatchRisk.HIGH
    assert pending.allowed is False
    assert pending.requires_approval is True
    assert approved.allowed is True
    assert any("approval" in reason for reason in approved.reasons)


def test_sensitive_paths_are_blocked():
    decision = DeveloperPolicy().evaluate(("config/.env",), additions=1, deletions=0)

    assert decision.risk is PatchRisk.BLOCKED
    assert decision.allowed is False
    assert "sensitive path" in decision.reasons[0]


def test_parent_traversal_and_absolute_paths_are_blocked():
    policy = DeveloperPolicy()

    traversal = policy.evaluate(("../app.py",), additions=1)
    absolute = policy.evaluate(("/tmp/app.py",), additions=1)
    windows = policy.evaluate(("src\\app.py",), additions=1)

    assert traversal.allowed is False
    assert absolute.allowed is False
    assert windows.allowed is False


def test_file_and_line_limits_are_hard_blocks():
    too_many_files = DeveloperPolicy(max_files=2).evaluate(
        ("a.py", "b.py", "c.py"), additions=1
    )
    too_many_lines = DeveloperPolicy(max_changed_lines=10).evaluate(
        ("a.py",), additions=8, deletions=3
    )

    assert too_many_files.risk is PatchRisk.BLOCKED
    assert too_many_lines.risk is PatchRisk.BLOCKED


def test_invalid_policy_limits_are_rejected():
    with pytest.raises(ValueError):
        DeveloperPolicy(max_files=0)
    with pytest.raises(ValueError):
        DeveloperPolicy(max_changed_lines=0)
