from __future__ import annotations

from dataclasses import dataclass
import ast
import hashlib
import os
import re
from pathlib import Path
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


@dataclass(frozen=True)
class CodeDependency:
    """A deterministic source-to-source dependency edge."""

    source: str
    target: str
    kind: str


class CodebaseIndexer:
    """Secure, deterministic local codebase index for developer workflows."""

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
    _IMPORT_RE = re.compile(r"(?:from\s+([\w./-]+)\s+import|import\s+([\w./-]+))")
    _JS_IMPORT_RE = re.compile(r"(?:from|import\s*\()\s*[\"']([^\"']+)[\"']|import\s+[\w*{}, ]+\s+from\s+[\"']([^\"']+)[\"']")

    def __init__(self, root: str | Path, *, workspace_id: UUID | None = None) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"codebase root is not a directory: {self.root}")
        self.workspace_id = workspace_id
        self._files: dict[str, CodeFile] = {}
        self._dependencies: tuple[CodeDependency, ...] = ()

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

    def _python_dependencies(self, file: CodeFile) -> tuple[str, ...]:
        try:
            tree = ast.parse(file.text, filename=file.path)
        except SyntaxError:
            return ()
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add("." * node.level + node.module)
        return tuple(sorted(modules))

    def _text_dependencies(self, file: CodeFile) -> tuple[str, ...]:
        modules: set[str] = set()
        for match in self._JS_IMPORT_RE.finditer(file.text):
            modules.update(group for group in match.groups() if group)
        return tuple(sorted(modules))

    def _resolve_local_target(self, source: CodeFile, imported: str) -> str | None:
        if imported.startswith("."):
            leading_dots = len(imported) - len(imported.lstrip("."))
            module = imported[leading_dots:].replace(".", "/")
            base_dir = Path(source.path).parent
            for _ in range(max(leading_dots - 1, 0)):
                base_dir = base_dir.parent
            base = base_dir / module
            candidates = [base]
            if base.suffix == "":
                candidates.extend(base.with_suffix(ext) for ext in (".py", ".js", ".jsx", ".ts", ".tsx"))
                candidates.append(base / "__init__.py")
            for candidate in candidates:
                normalized = candidate.as_posix()
                if normalized in self._files:
                    return normalized
            return None
        normalized = imported.replace(".", "/")
        candidates = [normalized]
        if "/" not in imported and source.language == "python":
            candidates.insert(0, (Path(source.path).parent / imported).as_posix())
        for candidate in candidates:
            for suffix in ("", ".py", ".js", ".jsx", ".ts", ".tsx"):
                path = candidate + suffix
                if path in self._files:
                    return path
        return None

    def _build_dependencies(self) -> tuple[CodeDependency, ...]:
        edges: set[tuple[str, str, str]] = set()
        for file in self._files.values():
            imported_modules = (
                self._python_dependencies(file)
                if file.language == "python"
                else self._text_dependencies(file)
            )
            for imported in imported_modules:
                target = self._resolve_local_target(file, imported)
                if target and target != file.path:
                    edges.add((file.path, target, "import"))
        return tuple(CodeDependency(*edge) for edge in sorted(edges))

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
        self._dependencies = self._build_dependencies()
        return tuple(sorted(indexed.values(), key=lambda item: item.path))

    def files(self) -> tuple[CodeFile, ...]:
        return tuple(sorted(self._files.values(), key=lambda item: item.path))

    def dependencies(self) -> tuple[CodeDependency, ...]:
        return self._dependencies

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
            "dependency_count": len(self._dependencies),
            "languages": dict(sorted(languages.items())),
        }
