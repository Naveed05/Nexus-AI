from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nexus.core.code_index import CodebaseIndexer
from nexus.core.developer_agent import DeveloperAgent
from nexus.core.developer_approval import DeveloperApproval
from nexus.core.developer_policy import DeveloperPolicy


def test_high_risk_execution_rejects_future_dated_approval(tmp_path: Path) -> None:
    agent = DeveloperAgent(CodebaseIndexer(tmp_path), policy=DeveloperPolicy(max_files=8, max_changed_lines=400))
    changes = {f"file{i}.py": ("old\n", "new\n") for i in range(5)}
    artifact = agent.build_patch_artifact(changes, approved=True)
    assert artifact.audit is not None
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    approval = DeveloperApproval.decide(
        artifact.audit.fingerprint,
        approved=True,
        actor="reviewer",
        reason="Reviewed the exact patch.",
        decided_at=future.isoformat(),
    )
    assert DeveloperAgent.authorize_patch_execution(artifact, approval=approval) is False


def test_high_risk_execution_accepts_current_approval(tmp_path: Path) -> None:
    agent = DeveloperAgent(CodebaseIndexer(tmp_path), policy=DeveloperPolicy(max_files=8, max_changed_lines=400))
    changes = {f"file{i}.py": ("old\n", "new\n") for i in range(5)}
    artifact = agent.build_patch_artifact(changes, approved=True)
    assert artifact.audit is not None
    approval = DeveloperApproval.decide(
        artifact.audit.fingerprint,
        approved=True,
        actor="reviewer",
        reason="Reviewed the exact patch.",
    )
    assert DeveloperAgent.authorize_patch_execution(artifact, approval=approval) is True


def test_execution_rejects_invalid_approval_time_configuration(tmp_path: Path) -> None:
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    artifact = agent.build_patch_artifact({"router.py": ("old\n", "new\n")})
    assert artifact.audit is not None
    approval = DeveloperApproval.pending(artifact.audit.fingerprint)
    invalid = replace(approval, decided_at="2026-09-16T18:00:00+00:00")
    assert invalid.is_time_valid(now=datetime(2026, 9, 16, 17, 59, 0, tzinfo=timezone.utc)) is False
