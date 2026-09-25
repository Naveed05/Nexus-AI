from pathlib import Path
from uuid import uuid4

from nexus.core.memory import MemoryStore
from nexus.core.workspace_intelligence import WorkspaceIntelligence
from nexus.core.workspaces import WorkspaceRegistry


def test_workspace_intelligence_summary_and_context_pack(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(tmp_path / "workspaces.sqlite3")
    memory = MemoryStore(tmp_path / "memory.sqlite3")
    workspace = registry.create(name="Analytics", owner_id="u1", metadata={"domain": "sales"})
    context = registry.context(workspace.workspace_id)
    context.add_file(uuid4())
    context.add_dataset(uuid4())
    registry.save_context(workspace.workspace_id)
    memory.remember("Sales data uses monthly revenue and churn.", workspace_id=workspace.workspace_id, tags=("data",), importance=0.9)

    intelligence = WorkspaceIntelligence(registry, memory)
    summary = intelligence.summary(workspace.workspace_id)
    pack = intelligence.context_pack(workspace.workspace_id, objective="revenue churn")

    assert summary["resources"]["files"] == 1
    assert summary["resources"]["datasets"] == 1
    assert summary["readiness"]["has_resources"] is True
    assert "Analytics" in pack["context"]
    assert "revenue" in pack["context"].lower()


def test_workspace_intelligence_restart_safe(tmp_path: Path) -> None:
    db = tmp_path / "workspaces.sqlite3"
    registry = WorkspaceRegistry(db)
    workspace = registry.create(name="Persistent")
    reopened = WorkspaceRegistry(db)
    intelligence = WorkspaceIntelligence(reopened, MemoryStore(tmp_path / "memory.sqlite3"))
    assert intelligence.readiness(workspace.workspace_id)["ready"] is False
