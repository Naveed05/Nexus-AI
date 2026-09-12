from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Protocol
from uuid import UUID

from .documents import DocumentChunk, DocumentWorkspace


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    """Dependency-free deterministic embedding baseline for local development."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

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


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _lexical_score(query: str, text: str) -> float:
    query_terms = set(re.findall(r"\w+", query.lower()))
    text_terms = re.findall(r"\w+", text.lower())
    if not query_terms or not text_terms:
        return 0.0
    counts = {term: text_terms.count(term) for term in query_terms}
    return sum(1.0 for value in counts.values() if value > 0) / len(query_terms)


@dataclass(frozen=True)
class RetrievalResult:
    chunk: DocumentChunk
    score: float
    vector_score: float = 0.0
    lexical_score: float = 0.0

    @property
    def citation(self) -> str:
        filename = self.chunk.metadata.get("filename", "document")
        return f"{filename} — chunk {self.chunk.index + 1}"


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
            self._items[chunk.chunk_id] = (chunk, vector)

    def search(self, vector: list[float], *, top_k: int = 5) -> list[tuple[DocumentChunk, float]]:
        if top_k <= 0:
            return []
        scored = [(chunk, _cosine(vector, stored)) for chunk, stored in self._items.values()]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]


class RetrievalEngine:
    """Workspace-scoped hybrid retrieval with deterministic reranking."""

    def __init__(self, documents: DocumentWorkspace, *, embeddings: EmbeddingProvider | None = None, store: VectorStore | None = None) -> None:
        self.documents = documents
        self.embeddings = embeddings or HashEmbeddingProvider()
        self.store = store or InMemoryVectorStore()
        self._chunk_workspace: dict[UUID, UUID | None] = {}

    def index_document(self, document_id: UUID) -> int:
        document = self.documents.get(document_id)
        chunks = list(self.documents.get_chunks(document_id))
        if not chunks:
            return 0
        self.store.upsert(chunks, self.embeddings.embed([chunk.text for chunk in chunks]))
        for chunk in chunks:
            self._chunk_workspace[chunk.chunk_id] = document.workspace_id
        return len(chunks)

    def search(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5) -> list[RetrievalResult]:
        if not query.strip() or top_k <= 0:
            return []
        candidates = self.store.search(self.embeddings.embed([query])[0], top_k=max(top_k * 8, top_k))
        filtered = [item for item in candidates if workspace_id is None or self._chunk_workspace.get(item[0].chunk_id) == workspace_id]
        results: list[RetrievalResult] = []
        for chunk, vector_score in filtered:
            lexical = _lexical_score(query, chunk.text)
            score = (0.7 * max(vector_score, 0.0)) + (0.3 * lexical)
            results.append(RetrievalResult(chunk=chunk, score=score, vector_score=vector_score, lexical_score=lexical))
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
