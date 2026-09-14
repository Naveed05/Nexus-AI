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
