from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
from typing import Iterable
from uuid import UUID


@dataclass(frozen=True)
class CodeFile:
    """Indexed source-file metadata and bounded text used by developer agents."""

    path: str
    language: str
    size_bytes: int
    line_count: int
    sha256: str
    text: str


@dataclass(frozen=True)
class CodeSearchResult:
    file: CodeFile
    score: float
    matches: tuple[str, ...]


class CodebaseIndexer:
    """Secure, deterministic local codebase index for developer workflows.

    The index intentionally stores bounded source text in memory. It is a foundation
    that can later be replaced by a persistent/vector-backed implementation without
    changing the developer-agent contract.
    """

    _LANGUAGES = {
        ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".go": "go",
        ".rs": "rust", ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".h": "c",
        ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby", ".php": "php",
        ".swift": "swift", ".kt": "kotlin", ".kts": "kotlin", ".sql": "sql",
        ".sh": "shell", ".bash": "shell", ".yaml": "yaml", ".yml": "yaml",
        ".json": "json", ".toml": "toml", ".md": "markdown",
    }
    _IGNORED_DIRS = {
        ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build",
        ".next", "coverage", ".nexus",
    }
    _SENSITIVE_NAMES = {".env", ".env.local", ".env.production", ".env.development"}
    _MAX_FILE_BYTES = 512_000
    _MAX_TEXT_CHARS = 500_000

    def __init__(self, root: str | Path, *, workspace_id: UUID | None = None) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"codebase root is not a directory: {self.root}")
        self.workspace_id = workspace_id
        self._files: dict[str, CodeFile] = {}

    def _safe_relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _iter_files(self) -> Iterable[Path]:
        for current, dirs, files in os.walk(self.root):
            dirs[:] = [name for name in dirs if name not in self._IGNORED_DIRS]
            for name in files:
                path = Path(current) / name
                if name in self._SENSITIVE_NAMES:
                    continue
                if path.suffix.lower() not in self._LANGUAGES:
                    continue
                try:
                    if path.stat().st_size > self._MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                yield path

    def build(self) -> tuple[CodeFile, ...]:
        indexed: dict[str, CodeFile] = {}
        for path in self._iter_files():
            try:
                payload = path.read_bytes()
                text = payload.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if len(text) > self._MAX_TEXT_CHARS:
                text = text[: self._MAX_TEXT_CHARS]
            relative = self._safe_relative(path)
            indexed[relative] = CodeFile(
                path=relative,
                language=self._LANGUAGES[path.suffix.lower()],
                size_bytes=len(payload),
                line_count=text.count("\n") + (1 if text else 0),
                sha256=hashlib.sha256(payload).hexdigest(),
                text=text,
            )
        self._files = indexed
        return tuple(sorted(indexed.values(), key=lambda item: item.path))

    def files(self) -> tuple[CodeFile, ...]:
        return tuple(sorted(self._files.values(), key=lambda item: item.path))

    def search(self, query: str, *, top_k: int = 10) -> tuple[CodeSearchResult, ...]:
        terms = tuple(term.lower() for term in query.split() if term.strip())
        if not terms:
            return ()
        results: list[CodeSearchResult] = []
        for file in self._files.values():
            haystack = f"{file.path}\n{file.text}".lower()
            matched = tuple(term for term in terms if term in haystack)
            if not matched:
                continue
            score = len(matched) / len(terms)
            if file.path.lower().find(query.lower()) >= 0:
                score += 0.25
            results.append(CodeSearchResult(file=file, score=min(score, 1.25), matches=matched))
        results.sort(key=lambda item: (-item.score, item.file.path))
        return tuple(results[: max(1, min(top_k, 50))])

    def summary(self) -> dict[str, object]:
        languages: dict[str, int] = {}
        for file in self._files.values():
            languages[file.language] = languages.get(file.language, 0) + 1
        return {
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "root": str(self.root),
            "file_count": len(self._files),
            "languages": dict(sorted(languages.items())),
        }
