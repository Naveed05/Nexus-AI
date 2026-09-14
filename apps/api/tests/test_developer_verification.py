from pathlib import Path

import pytest

from nexus.core.code_index import CodebaseIndexer
from nexus.core.developer_agent import DeveloperAgent, DeveloperVerificationPlan
from nexus.core.developer_verification import DeveloperVerificationService
from nexus.core.verification_runner import VerificationRunner


def test_verification_runner_rejects_non_generated_commands(tmp_path: Path):
    runner = VerificationRunner(tmp_path)

    with pytest.raises(ValueError, match="only generated"):
        runner.run("python -c 'print(1)'")


def test_verification_runner_executes_bounded_pytest(tmp_path: Path):
    (tmp_path / "test_smoke.py").write_text("def test_smoke():\n    assert 1 == 1\n", encoding="utf-8")
    runner = VerificationRunner(tmp_path)

    result = runner.run("PYTHONPATH=. pytest -q", timeout_seconds=30)

    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.timed_out is False
    assert "passed" in result.output


def test_verification_runner_preserves_extra_generated_pytest_args(tmp_path: Path):
    (tmp_path / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    runner = VerificationRunner(tmp_path)

    result = runner.run("PYTHONPATH=. pytest -q test_smoke.py", timeout_seconds=30)

    assert result.status == "passed"
    assert result.exit_code == 0
    assert "1 passed" in result.output


def test_developer_verification_service_normalizes_runner_result(tmp_path: Path):
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    runner = VerificationRunner(tmp_path)
    service = DeveloperVerificationService(agent, runner)
    plan = DeveloperVerificationPlan(
        focused_command="PYTHONPATH=. pytest -q",
        full_command="PYTHONPATH=. pytest -q",
        rationale=("test",),
    )
    (tmp_path / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")

    result = service.run(plan, focused=True, timeout_seconds=30)

    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.command == "PYTHONPATH=. pytest -q"


def test_developer_verification_service_reports_invalid_plan_command(tmp_path: Path):
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    runner = VerificationRunner(tmp_path)
    service = DeveloperVerificationService(agent, runner)
    plan = DeveloperVerificationPlan(
        focused_command="rm -rf .",
        full_command="PYTHONPATH=. pytest -q",
        rationale=("test",),
    )

    result = service.run(plan, focused=True)

    assert result.status == "failed"
    assert result.exit_code == 2
    assert "only generated" in result.output
