from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from uuid import UUID

from .code_index import CodeSearchResult, CodebaseIndexer
from .task import Task


class DeveloperAction(str, Enum):
    INSPECT = "inspect"
    DIAGNOSE = "diagnose"
    PATCH = "patch"
    TEST = "test"


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
    """Foundation for evidence-first code understanding and future code execution."""

    _ACTION_HINTS = {
        DeveloperAction.PATCH: ("fix", "change", "modify", "implement", "patch", "refactor"),
        DeveloperAction.TEST: ("test", "tests", "pytest", "verify", "coverage"),
        DeveloperAction.DIAGNOSE: ("bug", "error", "failure", "broken", "debug", "diagnose"),
    }

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
