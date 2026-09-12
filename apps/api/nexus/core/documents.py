from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from .artifacts import Artifact, LocalArtifactStore


class DocumentParseError(ValueError):
    """Raised when a document cannot be parsed."""


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)
    text: str = ""
    index: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("chunk text cannot be empty")
        if self.index < 0:
            raise ValueError("chunk index cannot be negative")


@dataclass(frozen=True)
class DocumentRef:
    document_id: UUID = field(default_factory=uuid4)
    workspace_id: UUID | None = None
    filename: str = "document"
    file_format: str = "txt"
    mime_type: str | None = None
    size_bytes: int = 0
    artifact_id: UUID | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.filename.strip():
            raise ValueError("filename cannot be empty")
        if self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")


class DocumentParser(Protocol):
    formats: tuple[str, ...]

    def parse(self, data: bytes, filename: str) -> str: ...


class PlainTextParser:
    formats = ("txt", "md", "markdown")

    def parse(self, data: bytes, filename: str) -> str:
        try:
            return data.decode("utf-8").replace("\r\n", "\n").strip()
        except UnicodeDecodeError as exc:
            raise DocumentParseError(f"Unable to decode {filename} as UTF-8") from exc


class DocumentChunker:
    """Deterministic character-window chunker with paragraph preference."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 150) -> None:
        if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("require 0 <= overlap < chunk_size and chunk_size > 0")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, document_id: UUID, text: str, metadata: dict[str, str] | None = None) -> list[DocumentChunk]:
        text = text.strip()
        if not text:
            return []
        chunks: list[DocumentChunk] = []
        start = 0
        index = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            if end < len(text):
                boundary = text.rfind("\n\n", start, end)
                if boundary > start + self.chunk_size // 2:
                    end = boundary
            piece = text[start:end].strip()
            if piece:
                chunks.append(DocumentChunk(document_id=document_id, text=piece, index=index, metadata=dict(metadata or {})))
                index += 1
            if end >= len(text):
                break
            start = max(0, end - self.overlap)
        return chunks


class DocumentWorkspace:
    """Workspace-aware document registry backed by the existing artifact store."""

    def __init__(self, root: str | Path, *, chunker: DocumentChunker | None = None) -> None:
        self.store = LocalArtifactStore(root)
        self.chunker = chunker or DocumentChunker()
        self.parsers: dict[str, DocumentParser] = {}
        self.documents: dict[UUID, DocumentRef] = {}
        self.chunks: dict[UUID, tuple[DocumentChunk, ...]] = {}
        self._register_parser(PlainTextParser())

    def _register_parser(self, parser: DocumentParser) -> None:
        for fmt in parser.formats:
            self.parsers[fmt.lower().lstrip(".")] = parser

    def register(self, data: bytes, *, filename: str, workspace_id: UUID | None = None, metadata: dict[str, str] | None = None) -> DocumentRef:
        suffix = Path(filename).suffix.lower().lstrip(".")
        parser = self.parsers.get(suffix)
        if parser is None:
            raise DocumentParseError(f"Unsupported document format: {suffix or 'unknown'}")
        text = parser.parse(data, filename)
        if not text:
            raise DocumentParseError("Document contains no readable text")
        artifact = self.store.put(data, filename=Path(filename).name, artifact_type="document", mime_type=None, metadata=metadata)
        document = DocumentRef(workspace_id=workspace_id, filename=artifact.filename, file_format=suffix, size_bytes=len(data), artifact_id=artifact.artifact_id, metadata=dict(metadata or {}))
        self.documents[document.document_id] = document
        self.chunks[document.document_id] = tuple(self.chunker.chunk(document.document_id, text, {"filename": document.filename, **document.metadata}))
        return document

    def get(self, document_id: UUID) -> DocumentRef:
        try:
            return self.documents[document_id]
        except KeyError as exc:
            raise DocumentParseError(f"Unknown document: {document_id}") from exc

    def get_chunks(self, document_id: UUID, *, workspace_id: UUID | None = None) -> tuple[DocumentChunk, ...]:
        document = self.get(document_id)
        if workspace_id is not None and document.workspace_id != workspace_id:
            raise DocumentParseError("Document does not belong to the requested workspace")
        return self.chunks[document_id]
