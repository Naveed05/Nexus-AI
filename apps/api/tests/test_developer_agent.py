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
