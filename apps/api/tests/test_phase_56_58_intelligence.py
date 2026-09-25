from pathlib import Path
from uuid import UUID

import pytest

from nexus.core.data_science import DataScienceService
from nexus.core.dataset_workspace import DatasetWorkspace
from nexus.core.files import FileRegistry, LocalFileStore
from nexus.core.knowledge import KnowledgeEngine
from nexus.core.knowledge_intelligence import KnowledgeIntelligenceService
from nexus.core.documents import DocumentWorkspace
from nexus.core.retrieval import HashEmbeddingProvider, JsonVectorStore, RetrievalEngine
from nexus.core.workspace_intelligence import WorkspaceIntelligenceService
from nexus.core.workspaces import WorkspaceRegistry


def test_workspace_intelligence_builds_restart_safe_resource_pack(tmp_path: Path) -> None:
    workspace_registry = WorkspaceRegistry(tmp_path / "workspaces.sqlite3")
    workspace = workspace_registry.create(name="Analytics", owner_id="user-1")
    files = FileRegistry(tmp_path / "files.sqlite3")
    file_store = LocalFileStore(tmp_path / "files")
    file_ref = file_store.put(b"name,value\na,1\n", filename="sales.csv", workspace_id=workspace.workspace_id)
    files.register(file_ref)
    workspace_registry.context(workspace.workspace_id).add_file(file_ref.file_id)

    datasets = DatasetWorkspace(tmp_path / "datasets")
    dataset = datasets.register(b"name,value\na,1\n", filename="sales.csv", file_format="csv")
    workspace_registry.context(workspace.workspace_id).add_dataset(dataset.dataset_id)
    workspace_registry.save_context(workspace.workspace_id)

    documents = DocumentWorkspace(tmp_path / "documents")
    document = documents.register(b"Revenue policy applies to verified orders.", filename="policy.txt", workspace_id=workspace.workspace_id)
    workspace_registry.context(workspace.workspace_id).add_document(document.document_id)
    workspace_registry.save_context(workspace.workspace_id)

    service = WorkspaceIntelligenceService(workspace_registry, files, datasets.registry, documents)
    report = service.inspect(workspace.workspace_id)

    assert report.resource_counts == {"files": 1, "datasets": 1, "documents": 1, "artifacts": 0}
    assert report.readiness["has_tabular_data"] is True
    assert report.readiness["has_searchable_knowledge"] is True
    assert "sales.csv" in report.context


def test_knowledge_intelligence_returns_citations_and_context(tmp_path: Path) -> None:
    documents = DocumentWorkspace(tmp_path / "documents")
    document = documents.register(
        b"NEXUS retention policy requires verified artifacts.\n\nRetention is workspace scoped.",
        filename="policy.txt",
        workspace_id=UUID(int=1),
    )
    engine = KnowledgeEngine(documents, tmp_path / "index.json")
    engine.retrieval.embeddings = HashEmbeddingProvider(64)
    engine.retrieval.store = JsonVectorStore(tmp_path / "index.json", embedding_signature="hash:64")
    engine.retrieval.index_document(document.document_id)

    service = KnowledgeIntelligenceService(engine)
    result = service.search(UUID(int=1), "verified artifacts", top_k=3)

    assert result.result_count >= 1
    assert result.citations
    assert "verified artifacts" in result.context


def test_data_science_service_reports_schema_quality_and_baseline(tmp_path: Path) -> None:
    workspace = DatasetWorkspace(tmp_path / "datasets")
    dataset = workspace.register(
        b"age,spend,target\n20,100,no\n25,120,no\n30,180,yes\n35,210,yes\n40,250,yes\n45,300,yes\n",
        filename="customers.csv",
        file_format="csv",
    )
    service = DataScienceService(workspace)
    report = service.inspect(dataset.dataset_id, target="target")

    assert report.profile["rows"] == 6
    assert report.problem["target"] == "target"
    assert report.recommendations
    baseline = service.baseline(dataset.dataset_id, "target")
    assert baseline["rows_used"] == 6
    assert "metrics" in baseline


def test_data_science_rejects_unknown_dataset(tmp_path: Path) -> None:
    service = DataScienceService(DatasetWorkspace(tmp_path / "datasets"))
    with pytest.raises(ValueError, match="Unknown dataset"):
        service.schema(UUID(int=9))
