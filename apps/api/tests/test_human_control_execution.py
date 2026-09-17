from pathlib import Path

import pytest

from nexus.core.code_index import CodebaseIndexer
from nexus.core.control_ledger import ControlLedger
from nexus.core.developer_agent import DeveloperAgent
from nexus.core.human_control import ControlRisk, HumanControlPolicy


def test_developer_boundary_requires_approval_for_high_risk_action(tmp_path: Path):
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    denied = agent.authorize_controlled_action("production_deploy")
    approved = agent.authorize_controlled_action("production_deploy", approved=True)
    assert denied.risk is ControlRisk.HIGH
    assert denied.allowed is False
    assert denied.requires_approval is True
    assert approved.risk is ControlRisk.HIGH
    assert approved.allowed is True
    assert approved.requires_approval is False


def test_developer_boundary_fails_closed_for_blocked_action(tmp_path: Path):
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    decision = agent.authorize_controlled_action("credential_exfiltration", approved=True)
    assert decision.risk is ControlRisk.BLOCKED
    assert decision.allowed is False
    assert decision.requires_approval is False


def test_developer_boundary_allows_medium_action(tmp_path: Path):
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    decision = agent.authorize_controlled_action("file_write")
    assert decision.risk is ControlRisk.MEDIUM
    assert decision.allowed is True


def test_custom_human_control_policy_is_used_at_boundary(tmp_path: Path):
    policy = HumanControlPolicy(blocked_actions=frozenset({"custom_block"}), high_risk_actions=frozenset({"custom_high"}), medium_risk_actions=frozenset())
    agent = DeveloperAgent(CodebaseIndexer(tmp_path), human_control=policy)
    assert agent.authorize_controlled_action("custom_block").allowed is False
    assert agent.authorize_controlled_action("custom_high").requires_approval is True


def test_empty_control_action_is_rejected_at_boundary(tmp_path: Path):
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    with pytest.raises(ValueError, match="action"):
        agent.authorize_controlled_action(" ")


def test_control_decision_is_persisted_in_tamper_evident_ledger(tmp_path: Path):
    ledger = ControlLedger(tmp_path / "controls.json")
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    decision = agent.authorize_controlled_action("production_deploy", actor="reviewer", ledger=ledger)
    assert decision.allowed is False
    events = ledger.load()
    assert len(events) == 1
    assert events[0].action == "production_deploy"
    assert events[0].actor == "reviewer"
    assert events[0].decision == "denied"
    assert ledger.verify() is True


def test_ledger_persistence_failure_denies_execution(tmp_path: Path):
    class BrokenLedger:
        def append(self, *args, **kwargs):
            raise OSError("disk unavailable")

    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    with pytest.raises(RuntimeError, match="ledger persistence failed"):
        agent.authorize_controlled_action("file_write", actor="system", ledger=BrokenLedger())


def test_allowed_decision_is_audited_before_execution_continues(tmp_path: Path):
    ledger = ControlLedger(tmp_path / "controls.json")
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    decision = agent.authorize_controlled_action("file_write", actor="system", ledger=ledger)
    assert decision.allowed is True
    event = ledger.load()[0]
    assert event.decision == "allowed"
    assert event.action == "file_write"
