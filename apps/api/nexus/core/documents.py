from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from .artifacts import LocalArtifactStore


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


class PDFParser:
    formats = ("pdf",)
    def parse(self, data: bytes, filename: str) -> str:
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
        except Exception as exc:
            raise DocumentParseError(f"Unable to parse {filename} as PDF") from exc
        if not text:
            raise DocumentParseError(f"No readable text found in {filename}")
        return text


class DOCXParser:
    formats = ("docx",)
    def parse(self, data: bytes, filename: str) -> str:
        try:
            from docx import Document
            import io
            document = Document(io.BytesIO(data))
            text = "\n\n".join(p.text.strip() for p in document.paragraphs if p.text.strip()).strip()
        except Exception as exc:
            raise DocumentParseError(f"Unable to parse {filename} as DOCX") from exc
        if not text:
            raise DocumentParseError(f"No readable text found in {filename}")
        return text


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
    """Workspace-aware document registry backed by artifacts and a durable manifest."""
    def __init__(self, root: str | Path, *, chunker: DocumentChunker | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = LocalArtifactStore(self.root)
        self.chunker = chunker or DocumentChunker()
        self.parsers: dict[str, DocumentParser] = {}
        self.documents: dict[UUID, DocumentRef] = {}
        self.chunks: dict[UUID, tuple[DocumentChunk, ...]] = {}
        self._manifest = self.root / "documents.json"
        self._register_parser(PlainTextParser())
        self._register_parser(PDFParser())
        self._register_parser(DOCXParser())
        self._load_manifest()

    def _register_parser(self, parser: DocumentParser) -> None:
        for fmt in parser.formats:
            self.parsers[fmt.lower().lstrip(".")] = parser

    def _load_manifest(self) -> None:
        if not self._manifest.exists():
            return
        try:
            payload = json.loads(self._manifest.read_text(encoding="utf-8"))
            for item in payload.get("documents", []):
                document = DocumentRef(document_id=UUID(item["document_id"]), workspace_id=UUID(item["workspace_id"]) if item.get("workspace_id") else None, filename=item["filename"], file_format=item["file_format"], mime_type=item.get("mime_type"), size_bytes=item["size_bytes"], artifact_id=UUID(item["artifact_id"]) if item.get("artifact_id") else None, metadata=item.get("metadata", {}), created_at=datetime.fromisoformat(item["created_at"]))
                self.documents[document.document_id] = document
                self.chunks[document.document_id] = tuple(DocumentChunk(chunk_id=UUID(chunk["chunk_id"]), document_id=document.document_id, text=chunk["text"], index=chunk["index"], metadata=chunk.get("metadata", {})) for chunk in item.get("chunks", []))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise DocumentParseError("Unable to load document manifest") from exc

    def _save_manifest(self) -> None:
        payload = {"documents": [{"document_id": str(doc.document_id), "workspace_id": str(doc.workspace_id) if doc.workspace_id else None, "filename": doc.filename, "file_format": doc.file_format, "mime_type": doc.mime_type, "size_bytes": doc.size_bytes, "artifact_id": str(doc.artifact_id) if doc.artifact_id else None, "metadata": doc.metadata, "created_at": doc.created_at.isoformat(), "chunks": [{"chunk_id": str(chunk.chunk_id), "text": chunk.text, "index": chunk.index, "metadata": chunk.metadata} for chunk in self.chunks.get(doc.document_id, ())]} for doc in self.documents.values()]}
        temporary = self._manifest.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self._manifest)

    def register(self, data: bytes, *, filename: str, workspace_id: UUID | None = None, metadata: dict[str, str] | None = None) -> DocumentRef:
        suffix = Path(filename).suffix.lower().lstrip(".")
        parser = self.parsers.get(suffix)
        if parser is None:
            raise DocumentParseError(f"Unsupported document format: {suffix or 'unknown'}")
        text = parser.parse(data, filename)
        artifact = self.store.put(data, filename=Path(filename).name, artifact_type="document", mime_type=None, metadata=metadata)
        document = DocumentRef(workspace_id=workspace_id, filename=artifact.filename, file_format=suffix, size_bytes=len(data), artifact_id=artifact.artifact_id, metadata=dict(metadata or {}))
        self.documents[document.document_id] = document
        self.chunks[document.document_id] = tuple(self.chunker.chunk(document.document_id, text, {"filename": document.filename, **document.metadata}))
        self._save_manifest()
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
