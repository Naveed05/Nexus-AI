from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Protocol
from uuid import UUID

from openai import OpenAI

from .config import settings
from .documents import DocumentChunk, DocumentWorkspace


class EmbeddingProvider(Protocol):
    @property
    def signature(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """Dependency-free deterministic embedding baseline for local development."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    @property
    def signature(self) -> str:
        return f"hash:{self.dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in re.findall(r"\w+", text.lower()):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                bucket = int.from_bytes(digest, "big") % self.dimensions
                vector[bucket] += 1.0
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / norm for value in vector] if norm else vector)
        return vectors


class OpenAIEmbeddingProvider:
    """Production embedding provider backed by the configured OpenAI embedding model."""

    def __init__(self, client: OpenAI | None = None, model: str | None = None) -> None:
        self._client = client
        self.model = model or settings.embedding_model

    @property
    def signature(self) -> str:
        return f"openai:{self.model}"

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._get_client().embeddings.create(model=self.model, input=texts)
        data = sorted(response.data, key=lambda item: item.index)
        if len(data) != len(texts):
            raise ValueError("Embedding provider returned an unexpected number of vectors")
        vectors = [list(item.embedding) for item in data]
        dimensions = len(vectors[0]) if vectors else 0
        if dimensions == 0 or any(len(vector) != dimensions for vector in vectors):
            raise ValueError("Embedding provider returned inconsistent vector dimensions")
        return vectors


def build_embedding_provider() -> EmbeddingProvider:
    """Select the configured provider, with a safe local fallback for development."""
    provider = settings.embedding_provider.strip().lower()
    if provider not in {"auto", "openai", "hash"}:
        raise ValueError("embedding_provider must be one of: auto, openai, hash")
    if provider == "hash":
        return HashEmbeddingProvider()
    if provider == "openai" or (provider == "auto" and settings.openai_api_key):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when embedding_provider=openai")
        return OpenAIEmbeddingProvider()
    return HashEmbeddingProvider()


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding vectors must have equal dimensions")
    return sum(a * b for a, b in zip(left, right))


def _lexical_score(query: str, text: str) -> float:
    query_terms = set(re.findall(r"\w+", query.lower()))
    text_terms = set(re.findall(r"\w+", text.lower()))
    if not query_terms or not text_terms:
        return 0.0
    return len(query_terms & text_terms) / len(query_terms)


@dataclass(frozen=True)
class RetrievalResult:
    chunk: DocumentChunk
    score: float
    vector_score: float = 0.0
    lexical_score: float = 0.0

    @property
    def citation(self) -> str:
        return f"{self.chunk.metadata.get('filename', 'document')} — chunk {self.chunk.index + 1}"


class VectorStore(Protocol):
    def upsert(self, chunks: list[DocumentChunk], vectors: list[list[float]]) -> None: ...
    def search(self, vector: list[float], *, top_k: int = 5) -> list[tuple[DocumentChunk, float]]: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._items: dict[UUID, tuple[DocumentChunk, list[float]]] = {}

    def upsert(self, chunks: list[DocumentChunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have equal length")
        for chunk, vector in zip(chunks, vectors):
            if not vector:
                raise ValueError("embedding vectors cannot be empty")
        for chunk, vector in zip(chunks, vectors):
            self._items[chunk.chunk_id] = (chunk, vector)

    def search(self, vector: list[float], *, top_k: int = 5) -> list[tuple[DocumentChunk, float]]:
        if top_k <= 0:
            return []
        scored = [(chunk, _cosine(vector, stored)) for chunk, stored in self._items.values()]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


class JsonVectorStore(InMemoryVectorStore):
    """Durable local vector store with atomic JSON persistence and index metadata."""

    SCHEMA_VERSION = 2

    def __init__(self, path: str | Path, *, embedding_signature: str | None = None) -> None:
        super().__init__()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_signature = embedding_signature
        self._loaded_signature: str | None = None
        self._load()

    @property
    def needs_rebuild(self) -> bool:
        return self.embedding_signature is not None and self._loaded_signature != self.embedding_signature

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != self.SCHEMA_VERSION:
                return
            self._loaded_signature = payload.get("embedding_signature")
            if self.embedding_signature is not None and self._loaded_signature != self.embedding_signature:
                return
            for item in payload.get("items", []):
                chunk = DocumentChunk(
                    chunk_id=UUID(item["chunk_id"]),
                    document_id=UUID(item["document_id"]),
                    text=item["text"],
                    index=item["index"],
                    metadata=item.get("metadata", {}),
                )
                self._items[chunk.chunk_id] = (chunk, [float(value) for value in item["vector"]])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Unable to load vector index") from exc

    def _save(self) -> None:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "embedding_signature": self.embedding_signature,
            "items": [
                {
                    "chunk_id": str(chunk.chunk_id),
                    "document_id": str(chunk.document_id),
                    "text": chunk.text,
                    "index": chunk.index,
                    "metadata": chunk.metadata,
                    "vector": vector,
                }
                for chunk, vector in self._items.values()
            ],
        }
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def upsert(self, chunks: list[DocumentChunk], vectors: list[list[float]]) -> None:
        super().upsert(chunks, vectors)
        self._save()


class RetrievalEngine:
    """Workspace-scoped hybrid retrieval with deterministic reranking."""

    def __init__(self, documents: DocumentWorkspace, *, embeddings: EmbeddingProvider | None = None, store: VectorStore | None = None) -> None:
        self.documents = documents
        self.embeddings = embeddings or build_embedding_provider()
        self.store = store or InMemoryVectorStore()
        if isinstance(self.store, JsonVectorStore):
            self.store.embedding_signature = self.embeddings.signature
            if self.store.needs_rebuild:
                self.store._items.clear()
                self.store._loaded_signature = self.embeddings.signature
        self._chunk_workspace: dict[UUID, UUID | None] = {}
        for document_id, document in documents.documents.items():
            for chunk in documents.get_chunks(document_id):
                self._chunk_workspace[chunk.chunk_id] = document.workspace_id

    def index_document(self, document_id: UUID) -> int:
        document = self.documents.get(document_id)
        chunks = list(self.documents.get_chunks(document_id))
        if not chunks:
            return 0
        self.store.upsert(chunks, self.embeddings.embed([chunk.text for chunk in chunks]))
        for chunk in chunks:
            self._chunk_workspace[chunk.chunk_id] = document.workspace_id
        return len(chunks)

    def rebuild(self) -> int:
        total = 0
        for document_id in self.documents.documents:
            total += self.index_document(document_id)
        return total

    def search(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5, document_id: UUID | None = None) -> list[RetrievalResult]:
        if not query.strip() or top_k <= 0:
            return []
        candidates = self.store.search(self.embeddings.embed([query])[0], top_k=max(top_k * 8, top_k))
        filtered = [
            item
            for item in candidates
            if (workspace_id is None or self._chunk_workspace.get(item[0].chunk_id) == workspace_id)
            and (document_id is None or item[0].document_id == document_id)
        ]
        results = []
        for chunk, vector_score in filtered:
            lexical = _lexical_score(query, chunk.text)
            results.append(RetrievalResult(chunk=chunk, score=0.7 * max(vector_score, 0.0) + 0.3 * lexical, vector_score=vector_score, lexical_score=lexical))
        results.sort(key=lambda item: (item.score, item.vector_score, -item.chunk.index), reverse=True)
        return results[:top_k]


class KnowledgeContextBuilder:
    """Builds compact, citation-bearing context from retrieved evidence."""

    def build(self, results: list[RetrievalResult], *, max_chars: int = 6000) -> str:
        if max_chars <= 0:
            return ""
        blocks: list[str] = []
        used = 0
        for result in results:
            block = f"[Source: {result.citation}]\n{result.chunk.text.strip()}"
            extra = len(block) + (2 if blocks else 0)
            if used + extra > max_chars:
                break
            blocks.append(block)
            used += extra
        return "\n\n".join(blocks)
