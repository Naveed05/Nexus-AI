from dataclasses import replace
from pathlib import Path

import pytest

from nexus.core.code_index import CodebaseIndexer
from nexus.core.developer_agent import DeveloperAgent
from nexus.core.developer_policy import DeveloperPolicy, PatchRisk


def test_patch_audit_declares_and_verifies_schema_version(tmp_path: Path) -> None:
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    artifact = agent.build_patch_artifact({"router.py": ("old\n", "new\n")})
    assert artifact.audit is not None
    assert artifact.audit.schema_version == DeveloperAgent.AUDIT_SCHEMA_VERSION
    assert artifact.audit.as_dict()["schema_version"] == "NEXUS-PATCH-AUDIT-V2"
    assert DeveloperAgent.verify_patch_audit(artifact) is True
    forged = replace(artifact, audit=replace(artifact.audit, schema_version="NEXUS-PATCH-AUDIT-V1"))
    assert DeveloperAgent.verify_patch_audit(forged) is False
    assert DeveloperAgent.authorize_patch_execution(forged) is False


def test_policy_blocks_private_key_material_in_added_content() -> None:
    decision = DeveloperPolicy().evaluate(("client.py",), additions=1, added_content="+-----BEGIN PRIVATE KEY-----\n")
    assert decision.risk is PatchRisk.BLOCKED
    assert decision.allowed is False
    assert "secret material" in decision.reasons[0]


def test_policy_blocks_high_confidence_provider_token_in_added_content() -> None:
    decision = DeveloperPolicy().evaluate(("client.py",), additions=1, added_content="+AWS_ACCESS_KEY_ID = 'AKIAIOSFODNN7EXAMPLE'\n")
    assert decision.risk is PatchRisk.BLOCKED
    assert decision.allowed is False


def test_policy_allows_normal_non_secret_configuration_text() -> None:
    decision = DeveloperPolicy().evaluate(("client.py",), additions=1, added_content="+API_KEY = os.environ.get('API_KEY')\n")
    assert decision.allowed is True
    assert decision.risk is PatchRisk.LOW


def test_agent_blocks_secret_material_even_when_path_is_not_sensitive(tmp_path: Path) -> None:
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    with pytest.raises(ValueError, match="secret material"):
        agent.build_patch_artifact({"client.py": ("def call():\n    return True\n", "def call():\n    return 'api_key = \\\"12345678901234567890\\\"'\n")})
