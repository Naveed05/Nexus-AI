from types import SimpleNamespace
from uuid import uuid4

import pytest

from nexus.core.config import settings
from nexus.core.documents import DocumentWorkspace
from nexus.core.retrieval import (
    HashEmbeddingProvider,
    JsonVectorStore,
    OpenAIEmbeddingProvider,
    RetrievalEngine,
    build_embedding_provider,
)


def test_json_vector_store_persists_embedding_metadata(tmp_path):
    workspace = DocumentWorkspace(tmp_path / "documents")
    document = workspace.register(b"NEXUS knowledge retrieval", filename="notes.txt")
    path = tmp_path / "index.json"
    engine = RetrievalEngine(
        workspace,
        embeddings=HashEmbeddingProvider(16),
        store=JsonVectorStore(path),
    )
    assert engine.index_document(document.document_id) == 1

    restored = JsonVectorStore(path, embedding_signature="hash:16")
    assert not restored.needs_rebuild
    assert len(restored._items) == 1


def test_json_vector_store_requires_rebuild_when_embedding_changes(tmp_path):
    workspace = DocumentWorkspace(tmp_path / "documents")
    document = workspace.register(b"NEXUS knowledge retrieval", filename="notes.txt")
    path = tmp_path / "index.json"
    engine = RetrievalEngine(workspace, embeddings=HashEmbeddingProvider(8), store=JsonVectorStore(path))
    engine.index_document(document.document_id)

    changed = JsonVectorStore(path, embedding_signature="hash:16")
    assert changed.needs_rebuild


def test_retrieval_engine_rebuilds_all_persisted_documents(tmp_path):
    workspace = DocumentWorkspace(tmp_path / "documents")
    first = workspace.register(b"alpha knowledge", filename="alpha.txt")
    second = workspace.register(b"beta knowledge", filename="beta.txt")
    engine = RetrievalEngine(workspace, embeddings=HashEmbeddingProvider(16), store=JsonVectorStore(tmp_path / "index.json"))

    assert engine.rebuild() == 2
    assert len(engine.search("alpha", top_k=1)) == 1
    assert engine.search("alpha", top_k=1)[0].chunk.document_id == first.document_id
    assert second.document_id != first.document_id


def test_build_embedding_provider_uses_hash_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "auto")
    monkeypatch.setattr(settings, "openai_api_key", None)
    assert isinstance(build_embedding_provider(), HashEmbeddingProvider)


def test_build_embedding_provider_requires_key_for_explicit_openai(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_embedding_provider()


def test_openai_embedding_provider_preserves_input_order():
    class Embeddings:
        def create(self, *, model, input):
            assert model == "text-embedding-3-small"
            assert input == ["first", "second"]
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                    SimpleNamespace(index=0, embedding=[1.0, 0.0]),
                ]
            )

    client = SimpleNamespace(embeddings=Embeddings())
    provider = OpenAIEmbeddingProvider(client=client, model="text-embedding-3-small")
    assert provider.signature == "openai:text-embedding-3-small"
    assert provider.embed(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
