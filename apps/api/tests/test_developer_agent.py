from pathlib import Path
from uuid import uuid4

from nexus.core.code_index import CodebaseIndexer
from nexus.core.developer_agent import DeveloperAction, DeveloperAgent
from nexus.core.task import Task


def test_developer_agent_prepares_evidence_backed_context(tmp_path: Path):
    (tmp_path / "router.py").write_text(
        "class TaskRouter:\n    def route(self, task):\n        return task\n", encoding="utf-8"
    )
    workspace_id = uuid4()
    agent = DeveloperAgent(CodebaseIndexer(tmp_path, workspace_id=workspace_id))
    task = Task(workspace_id=workspace_id, objective="diagnose the router bug")

    context = agent.prepare(task, query="TaskRouter route")

    assert context.action is DeveloperAction.DIAGNOSE
    assert context.workspace_id == workspace_id
    assert context.matches[0].file.path == "router.py"
    prompt = context.as_prompt_context()
    assert "DEVELOPER CODE CONTEXT:" in prompt
    assert "router.py" in prompt


def test_developer_agent_infers_core_actions():
    assert DeveloperAgent.infer_action("inspect this repository") is DeveloperAction.INSPECT
    assert DeveloperAgent.infer_action("fix the failing implementation") is DeveloperAction.PATCH
    assert DeveloperAgent.infer_action("run tests and verify") is DeveloperAction.TEST
    assert DeveloperAgent.infer_action("debug this error") is DeveloperAction.DIAGNOSE


def test_developer_agent_diagnoses_failure_with_code_evidence(tmp_path: Path):
    (tmp_path / "executor.py").write_text(
        "def execute(task):\n    raise ValueError('invalid task')\n", encoding="utf-8"
    )
    (tmp_path / "router.py").write_text(
        "def route(task):\n    return execute(task)\n", encoding="utf-8"
    )
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))

    diagnosis = agent.diagnose("ValueError in executor.py: invalid task")

    assert diagnosis.likely_files
    assert "executor.py" in diagnosis.likely_files
    assert diagnosis.confidence > 0
    assert any("executor.py" in item for item in diagnosis.evidence)
    assert diagnosis.as_dict()["symptom"]


def test_developer_agent_builds_reviewable_dependency_aware_patch_plan(tmp_path: Path):
    (tmp_path / "router.py").write_text(
        "from service import run\ndef route(task):\n    return run(task)\n", encoding="utf-8"
    )
    (tmp_path / "service.py").write_text("def run(task):\n    return task\n", encoding="utf-8")
    agent = DeveloperAgent(CodebaseIndexer(tmp_path))
    task = Task(objective="fix the router implementation")

    plan = agent.plan_patch(task, query="route", depth=1)

    assert plan.target_files
    assert "router.py" in plan.target_files
    assert "service.py" in plan.dependency_files
    assert plan.validation == (
        "Run the focused regression tests for the changed behavior.",
        "Run the broader API test suite before merging.",
    )
    assert plan.confidence > 0
    assert plan.as_dict()["steps"]
