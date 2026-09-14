from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from uuid import UUID

from .code_index import CodeSearchResult, CodebaseIndexer
from .task import Task


class DeveloperAction(str, Enum):
    INSPECT = "inspect"
    DIAGNOSE = "diagnose"
    PATCH = "patch"
    TEST = "test"


@dataclass(frozen=True)
class DeveloperDiagnostic:
    """Evidence-backed diagnosis candidate derived from an observed failure."""

    symptom: str
    likely_files: tuple[str, ...]
    evidence: tuple[str, ...]
    confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "symptom": self.symptom,
            "likely_files": list(self.likely_files),
            "evidence": list(self.evidence),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class DeveloperPatchPlan:
    """A reviewable patch plan; it never writes to the workspace by itself."""

    objective: str
    target_files: tuple[str, ...]
    dependency_files: tuple[str, ...]
    steps: tuple[str, ...]
    validation: tuple[str, ...]
    confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "target_files": list(self.target_files),
            "dependency_files": list(self.dependency_files),
            "steps": list(self.steps),
            "validation": list(self.validation),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class DeveloperPatchArtifact:
    """A concrete, reviewable unified diff generated without mutating files."""

    files: tuple[str, ...]
    diff: str
    additions: int
    deletions: int

    def as_dict(self) -> dict[str, object]:
        return {
            "files": list(self.files),
            "diff": self.diff,
            "additions": self.additions,
            "deletions": self.deletions,
        }


@dataclass(frozen=True)
class DeveloperVerificationPlan:
    """Safe validation commands derived from a developer patch plan."""

    focused_command: str
    full_command: str
    rationale: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "focused_command": self.focused_command,
            "full_command": self.full_command,
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True)
class DeveloperImpactReport:
    """Deterministic change-impact evidence derived from the dependency graph."""

    changed_files: tuple[str, ...]
    affected_files: tuple[str, ...]
    affected_count: int
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "changed_files": list(self.changed_files),
            "affected_files": list(self.affected_files),
            "affected_count": self.affected_count,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class DeveloperVerificationResult:
    """Structured verification evidence; execution is intentionally external."""

    command: str
    status: str
    exit_code: int | None
    output: str
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "output": self.output,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class DeveloperContext:
    """Evidence-backed code context prepared for a developer workflow."""

    action: DeveloperAction
    objective: str
    workspace_id: UUID | None
    repository_summary: dict[str, object]
    matches: tuple[CodeSearchResult, ...]

    def as_prompt_context(self, *, max_chars: int = 12_000) -> str:
        lines = [
            "DEVELOPER CODE CONTEXT:",
            f"Action: {self.action.value}",
            f"Objective: {self.objective}",
            f"Repository: {self.repository_summary}",
        ]
        for match in self.matches:
            lines.append(
                f"[File: {match.file.path} | language={match.file.language} | score={match.score:.2f}]\n"
                f"{match.file.text[:2500]}"
            )
        return "\n\n".join(lines)[:max_chars]


class DeveloperAgent:
    """Evidence-first code understanding, diagnosis, and future code execution."""

    _ACTION_HINTS = {
        DeveloperAction.PATCH: ("fix", "change", "modify", "implement", "patch", "refactor"),
        DeveloperAction.TEST: ("test", "tests", "pytest", "verify", "coverage"),
        DeveloperAction.DIAGNOSE: ("bug", "error", "failure", "broken", "debug", "diagnose"),
    }
    _ERROR_RE = re.compile(
        r"(?:error|exception|failure|failed|traceback|assertionerror|typeerror|valueerror|keyerror)\b[^\n]{0,180}",
        re.IGNORECASE,
    )
    _SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_.\-/]+$")

    def __init__(self, indexer: CodebaseIndexer) -> None:
        self.indexer = indexer

    @classmethod
    def infer_action(cls, objective: str) -> DeveloperAction:
        lowered = objective.lower()
        for action in (DeveloperAction.PATCH, DeveloperAction.TEST, DeveloperAction.DIAGNOSE):
            if any(hint in lowered for hint in cls._ACTION_HINTS[action]):
                return action
        return DeveloperAction.INSPECT

    def prepare(self, task: Task, *, query: str | None = None, top_k: int = 8) -> DeveloperContext:
        if task.workspace_id is not None and self.indexer.workspace_id not in (None, task.workspace_id):
            raise ValueError("code index belongs to a different workspace")
        if not self.indexer.files():
            self.indexer.build()
        search_query = query or task.objective
        matches = self.indexer.search(search_query, top_k=top_k)
        return DeveloperContext(
            action=self.infer_action(task.objective),
            objective=task.objective,
            workspace_id=task.workspace_id,
            repository_summary=self.indexer.summary(),
            matches=matches,
        )

    def diagnose(self, failure: str, *, top_k: int = 5) -> DeveloperDiagnostic:
        """Turn a test/runtime failure into a bounded, evidence-backed diagnosis candidate."""
        if not self.indexer.files():
            self.indexer.build()
        symptom_match = self._ERROR_RE.search(failure.strip())
        symptom = symptom_match.group(0).strip() if symptom_match else failure.strip()[:240]
        query_terms = re.findall(r"[A-Za-z_][A-Za-z0-9_.:/-]{2,}", failure)
        query = " ".join(dict.fromkeys(query_terms[-8:]))
        matches = self.indexer.search(query, top_k=top_k) if query else ()
        evidence = tuple(
            f"{match.file.path}: matched {', '.join(match.matches)} (score={match.score:.2f})"
            for match in matches
        )
        confidence = min(1.0, 0.25 + 0.15 * len(matches)) if matches else 0.0
        return DeveloperDiagnostic(
            symptom=symptom,
            likely_files=tuple(match.file.path for match in matches),
            evidence=evidence,
            confidence=round(confidence, 2),
        )

    def plan_patch(self, task: Task, *, query: str | None = None, depth: int = 1, top_k: int = 5) -> DeveloperPatchPlan:
        """Create a bounded, reviewable patch plan without modifying source files."""
        context = self.prepare(task, query=query, top_k=top_k)
        targets = tuple(match.file.path for match in context.matches)
        dependencies: list[str] = []
        for target in targets:
            for neighbor in self.indexer.dependency_neighbors(target, depth=depth):
                if neighbor not in targets and neighbor not in dependencies:
                    dependencies.append(neighbor)
        steps = (
            "Inspect the highest-ranked source matches and their local dependency neighborhood.",
            "Identify the smallest source change that satisfies the objective without touching unrelated files.",
            "Keep the patch reviewable and do not modify secrets or ignored workspace files.",
        )
        validation = (
            "Run the focused regression tests for the changed behavior.",
            "Run the broader API test suite before merging.",
        )
        confidence = round(min(1.0, 0.35 + 0.12 * len(targets) + 0.05 * len(dependencies)), 2)
        return DeveloperPatchPlan(
            objective=task.objective,
            target_files=targets,
            dependency_files=tuple(sorted(dependencies)),
            steps=steps,
            validation=validation,
            confidence=confidence,
        )

    def build_patch_artifact(
        self,
        changes: dict[str, tuple[str, str]],
        *,
        context_lines: int = 3,
    ) -> DeveloperPatchArtifact:
        """Build a unified diff from explicit before/after text without writing files."""
        if context_lines < 0 or context_lines > 20:
            raise ValueError("context_lines must be between 0 and 20")
        import difflib

        chunks: list[str] = []
        additions = 0
        deletions = 0
        for path in sorted(changes):
            if not path or not self._SAFE_PATH_RE.fullmatch(path) or path.startswith("/") or ".." in Path(path).parts:
                raise ValueError(f"unsafe patch path: {path}")
            before, after = changes[path]
            diff = list(difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=context_lines,
            ))
            additions += sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
            deletions += sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
            if diff:
                chunks.append("".join(diff))
        return DeveloperPatchArtifact(
            files=tuple(sorted(changes)),
            diff="\n".join(chunks),
            additions=additions,
            deletions=deletions,
        )

    def build_verification_plan(self, patch: DeveloperPatchPlan) -> DeveloperVerificationPlan:
        """Translate a patch plan into deterministic, non-executing validation commands."""
        focused = "PYTHONPATH=. pytest -q"
        full = "PYTHONPATH=. pytest -q"
        rationale = (
            f"Focused validation covers the changed behavior in {len(patch.target_files)} target file(s).",
            "Full validation reuses the repository API suite defined by CI.",
            "Commands are returned for review; this method does not execute shell commands.",
        )
        return DeveloperVerificationPlan(
            focused_command=focused,
            full_command=full,
            rationale=rationale,
        )

    def analyze_impact(self, changed_files: tuple[str, ...], *, depth: int = 1) -> DeveloperImpactReport:
        """Report downstream local files affected by a proposed change."""
        if depth < 1:
            raise ValueError("depth must be at least 1")
        normalized = tuple(sorted(dict.fromkeys(changed_files)))
        reverse: dict[str, set[str]] = {}
        for edge in self.indexer.dependencies():
            reverse.setdefault(edge.target, set()).add(edge.source)
        seen = set(normalized)
        frontier = set(normalized)
        for _ in range(depth):
            next_frontier: set[str] = set()
            for current in frontier:
                next_frontier.update(reverse.get(current, set()) - seen)
            seen.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        affected = tuple(sorted(seen - set(normalized)))
        evidence = tuple(
            f"{changed}: downstream local files include {', '.join(sorted(reverse.get(changed, set())))}"
            for changed in normalized
            if reverse.get(changed)
        )
        return DeveloperImpactReport(
            changed_files=normalized,
            affected_files=affected,
            affected_count=len(affected),
            evidence=evidence,
        )

    @staticmethod
    def verification_result(
        command: str,
        *,
        exit_code: int | None,
        output: str,
    ) -> DeveloperVerificationResult:
        """Normalize externally collected command output into verification evidence."""
        if not command.strip():
            raise ValueError("command must not be empty")
        if exit_code is None:
            status = "not_run"
        elif exit_code == 0:
            status = "passed"
        else:
            status = "failed"
        evidence = (
            "Verification status is derived solely from the supplied exit code.",
            "Command output is preserved as evidence; no command is executed here.",
        )
        return DeveloperVerificationResult(
            command=command.strip(),
            status=status,
            exit_code=exit_code,
            output=output,
            evidence=evidence,
        )
