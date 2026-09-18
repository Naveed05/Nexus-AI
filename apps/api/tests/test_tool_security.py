import pytest

from nexus.core.tool_security import ToolSecurityPolicy


def test_tool_security_rejects_restricted_argument_names() -> None:
    policy = ToolSecurityPolicy()
    with pytest.raises(ValueError, match="restricted fields"):
        policy.validate({"password": "do-not-pass"})


def test_tool_security_enforces_argument_size() -> None:
    policy = ToolSecurityPolicy(max_argument_bytes=10)
    with pytest.raises(ValueError, match="security limit"):
        policy.validate({"text": "this is too large"})


def test_tool_security_normalizes_restriction_names() -> None:
    policy = ToolSecurityPolicy(denied_argument_names=frozenset({" Secret "}))
    with pytest.raises(ValueError, match="restricted fields"):
        policy.validate({"secret": "x"})
