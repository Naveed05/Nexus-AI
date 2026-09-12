from tempfile import TemporaryDirectory
from uuid import UUID

from nexus.api.main import _build_task, client, file_registry, retrieval_engine, workspace_registry
from nexus.core.documents import DocumentChunker, DocumentWorkspace
from nexus.core.knowledge import KnowledgeEngine, KnowledgeTool
from nexus.core.retrieval import HashEmbeddingProvider, InMemoryVectorStore, JsonVectorStore, KnowledgeContextBuilder, RetrievalEngine
from nexus.core.schemas import TaskCreate


def test_workspace_task_receives_resource_context() -> None:
    workspace = workspace_registry.create(name="Analytics")
    upload = client.post(f"/api/v1/workspaces/{workspace.workspace_id}/files", files={"file": ("notes.txt", b"workspace notes", "text/plain")})
    assert upload.status_code == 201
    file_id = UUID(upload.json()["file_id"])
    task = _build_task(TaskCreate(objective="Use the workspace file", workspace_id=workspace.workspace_id))
    assert task.workspace_id == workspace.workspace_id
    assert f"workspace_id: {workspace.workspace_id}" in (task.context or "")
    assert str(file_id) in (task.context or "")


def test_task_rejects_unknown_workspace() -> None:
    unknown = UUID("00000000-0000-0000-0000-000000000001")
    assert client.post("/api/v1/tasks", json={"objective": "Inspect workspace", "workspace_id": str(unknown)}).status_code == 404


def test_workspace_task_response_exposes_workspace_id() -> None:
    workspace = workspace_registry.create(name="Research")
    response = client.post("/api/v1/tasks", json={"objective": "Summarize workspace", "workspace_id": str(workspace.workspace_id)})
    assert response.status_code == 201
    assert response.json()["workspace_id"] == str(workspace.workspace_id)


def test_workspace_file_lifecycle_and_isolation() -> None:
    workspace = workspace_registry.create(name="Files")
    other_workspace = workspace_registry.create(name="Other")
    upload = client.post(f"/api/v1/workspaces/{workspace.workspace_id}/files", files={"file": ("report.txt", b"hello nexus", "text/plain")})
    assert upload.status_code == 201
    file_id = UUID(upload.json()["file_id"])
    assert client.get(f"/api/v1/workspaces/{workspace.workspace_id}/files/{file_id}").content == b"hello nexus"
    assert client.get(f"/api/v1/workspaces/{other_workspace.workspace_id}/files/{file_id}").status_code == 404
    assert client.delete(f"/api/v1/workspaces/{workspace.workspace_id}/files/{file_id}").status_code == 204
    assert file_id not in workspace_registry.context(workspace.workspace_id).file_ids
    assert file_id not in {item.file_id for item in file_registry.list()}


def test_document_upload_indexes_chunks_and_exposes_context() -> None:
    workspace = workspace_registry.create(name="Knowledge")
    response = client.post(f"/api/v1/workspaces/{workspace.workspace_id}/documents", files={"file": ("guide.md", b"# NEXUS\n\nAgentic AI workspace with verified execution.", "text/markdown")})
    assert response.status_code == 201
    body = response.json(); document_id = UUID(body["document_id"])
    assert body["workspace_id"] == str(workspace.workspace_id) and body["file_format"] == "md"
    assert body["chunk_count"] >= 1 and document_id in workspace_registry.context(workspace.workspace_id).document_ids


def test_workspace_search_isolation() -> None:
    first = workspace_registry.create(name="First"); second = workspace_registry.create(name="Second")
    client.post(f"/api/v1/workspaces/{first.workspace_id}/documents", files={"file": ("first.txt", b"quantum computing research notes", "text/plain")})
    client.post(f"/api/v1/workspaces/{second.workspace_id}/documents", files={"file": ("second.txt", b"marine biology field notes", "text/plain")})
    results = client.post(f"/api/v1/workspaces/{first.workspace_id}/search", json={"query": "quantum computing", "top_k": 5}).json()
    assert results["results"] and all(UUID(item["document_id"]) in workspace_registry.context(first.workspace_id).document_ids for item in results["results"])
    assert {"citation", "vector_score", "lexical_score"}.issubset(results["results"][0])
    assert "[Source:" in results["context"]


def test_retrieval_embedding_is_reproducible() -> None:
    provider = HashEmbeddingProvider(dimensions=64)
    assert provider.embed(["NEXUS agentic workspace"])[0] == provider.embed(["NEXUS agentic workspace"])[0]


def test_hybrid_retrieval_rewards_exact_terms() -> None:
    with TemporaryDirectory() as root:
        docs = DocumentWorkspace(root, chunker=DocumentChunker(chunk_size=500, overlap=20))
        first = docs.register(b"Astra orchestrates complex research workflows.", filename="astra.txt")
        second = docs.register(b"General research workflows are useful.", filename="general.txt")
        engine = RetrievalEngine(docs, embeddings=HashEmbeddingProvider(dimensions=64), store=InMemoryVectorStore())
        engine.index_document(first.document_id); engine.index_document(second.document_id)
        results = engine.search("Astra research", top_k=2)
        assert results[0].chunk.document_id == first.document_id and results[0].lexical_score > 0


def test_grounded_context_contains_source_citations() -> None:
    with TemporaryDirectory() as root:
        docs = DocumentWorkspace(root)
        doc = docs.register(b"NEXUS uses grounded evidence.", filename="knowledge.txt")
        engine = RetrievalEngine(docs, store=InMemoryVectorStore()); engine.index_document(doc.document_id)
        results = engine.search("grounded evidence", top_k=1)
        context = KnowledgeContextBuilder().build(results, max_chars=4000)
        assert "[Source:" in context and results[0].citation in context


def test_json_vector_store_survives_reopen() -> None:
    with TemporaryDirectory() as root:
        docs = DocumentWorkspace(root)
        doc = docs.register(b"persistent knowledge survives restart", filename="persist.txt")
        path = f"{root}/index.json"
        first = RetrievalEngine(docs, store=JsonVectorStore(path)); first.index_document(doc.document_id)
        reopened = JsonVectorStore(path)
        assert reopened.search(HashEmbeddingProvider().embed(["persistent knowledge"])[0], top_k=1)[0][0].document_id == doc.document_id


def test_pdf_and_docx_parsers_are_registered() -> None:
    with TemporaryDirectory() as root:
        docs = DocumentWorkspace(root)
        assert "pdf" in docs.parsers and "docx" in docs.parsers


def test_unsupported_document_format_is_rejected() -> None:
    workspace = workspace_registry.create(name="Unsupported")
    response = client.post(f"/api/v1/workspaces/{workspace.workspace_id}/documents", files={"file": ("slides.pptx", b"not supported", "application/vnd.openxmlformats-officedocument.presentationml.presentation")})
    assert response.status_code == 415


def test_knowledge_engine_ingest_search_and_tool() -> None:
    with TemporaryDirectory() as root:
        docs = DocumentWorkspace(Path(root) / "documents")
        engine = KnowledgeEngine(docs, Path(root) / "knowledge.json")
        workspace_id = UUID("00000000-0000-0000-0000-000000000123")
        document, chunks = engine.ingest(b"NEXUS provides grounded research evidence.", filename="research.txt", workspace_id=workspace_id)
        assert chunks == 1
        result = engine.search("grounded research", workspace_id=workspace_id, top_k=1)
        assert result.results and result.results[0].chunk.document_id == document.document_id
        tool = KnowledgeTool(engine, lambda: workspace_id)
        payload = tool.execute("research evidence", top_k=1)
        assert payload["results"][0]["document_id"] == str(document.document_id)
