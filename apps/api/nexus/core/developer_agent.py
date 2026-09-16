from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib
import re
from uuid import UUID

from .code_index import CodeSearchResult, CodebaseIndexer
from .developer_approval import DeveloperApproval
from .developer_policy import DeveloperPolicy, DeveloperPolicyDecision, PatchRisk
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
        return {"symptom": self.symptom, "likely_files": list(self.likely_files), "evidence": list(self.evidence), "confidence": self.confidence}


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
        return {"objective": self.objective, "target_files": list(self.target_files), "dependency_files": list(self.dependency_files), "steps": list(self.steps), "validation": list(self.validation), "confidence": self.confidence}


@dataclass(frozen=True)
class DeveloperPatchAudit:
    """Stable, non-secret audit metadata for a proposed patch."""
    fingerprint: str
    file_count: int
    changed_lines: int
    risk: str
    allowed: bool
    requires_approval: bool
    schema_version: str = "NEXUS-PATCH-AUDIT-V2"
    def as_dict(self) -> dict[str, object]:
        return {"fingerprint": self.fingerprint, "file_count": self.file_count, "changed_lines": self.changed_lines, "risk": self.risk, "allowed": self.allowed, "requires_approval": self.requires_approval, "schema_version": self.schema_version}


@dataclass(frozen=True)
class DeveloperPatchArtifact:
    """A concrete, policy-checked unified diff generated without mutating files."""
    files: tuple[str, ...]
    diff: str
    additions: int
    deletions: int
    policy: DeveloperPolicyDecision | None = None
    audit: DeveloperPatchAudit | None = None
    def as_dict(self) -> dict[str, object]:
        return {"files": list(self.files), "diff": self.diff, "additions": self.additions, "deletions": self.deletions, "policy": self.policy.as_dict() if self.policy else None, "audit": self.audit.as_dict() if self.audit else None}


@dataclass(frozen=True)
class DeveloperVerificationPlan:
    """Safe validation commands derived from a developer patch plan."""
    focused_command: str
    full_command: str
    rationale: tuple[str, ...]
    def as_dict(self) -> dict[str, object]:
        return {"focused_command": self.focused_command, "full_command": self.full_command, "rationale": list(self.rationale)}


@dataclass(frozen=True)
class DeveloperImpactReport:
    """Deterministic change-impact evidence derived from the dependency graph."""
    changed_files: tuple[str, ...]
    affected_files: tuple[str, ...]
    affected_count: int
    evidence: tuple[str, ...]
    def as_dict(self) -> dict[str, object]:
        return {"changed_files": list(self.changed_files), "affected_files": list(self.affected_files), "affected_count": self.affected_count, "evidence": list(self.evidence)}


@dataclass(frozen=True)
class DeveloperVerificationResult:
    """Structured verification evidence; execution is intentionally external."""
    command: str
    status: str
    exit_code: int | None
    output: str
    evidence: tuple[str, ...]
    def as_dict(self) -> dict[str, object]:
        return {"command": self.command, "status": self.status, "exit_code": self.exit_code, "output": self.output, "evidence": list(self.evidence)}


@dataclass(frozen=True)
class DeveloperContext:
    """Evidence-backed code context prepared for a developer workflow."""
    action: DeveloperAction
    objective: str
    workspace_id: UUID | None
    repository_summary: dict[str, object]
    matches: tuple[CodeSearchResult, ...]
    def as_prompt_context(self, *, max_chars: int = 12_000) -> str:
        lines = ["DEVELOPER CODE CONTEXT:", f"Action: {self.action.value}", f"Objective: {self.objective}", f"Repository: {self.repository_summary}"]
        for match in self.matches:
            lines.append(f"[File: {match.file.path} | language={match.file.language} | score={match.score:.2f}]\n{match.file.text[:2500]}")
        return "\n\n".join(lines)[:max_chars]


class DeveloperAgent:
    """Evidence-first code understanding, diagnosis, and future code execution."""
    AUDIT_SCHEMA_VERSION = "NEXUS-PATCH-AUDIT-V2"
    APPROVAL_MAX_AGE_SECONDS = 3600
    _ACTION_HINTS = {DeveloperAction.PATCH: ("fix", "change", "modify", "implement", "patch", "refactor"), DeveloperAction.TEST: ("test", "tests", "pytest", "verify", "coverage"), DeveloperAction.DIAGNOSE: ("bug", "error", "failure", "broken", "debug", "diagnose")}
    _ERROR_RE = re.compile(r"(?:error|exception|failure|failed|traceback|assertionerror|typeerror|valueerror|keyerror)\b[^\n]{0,180}", re.IGNORECASE)
    _SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_.\-/]+$")

    def __init__(self, indexer: CodebaseIndexer, *, policy: DeveloperPolicy | None = None) -> None:
        self.indexer = indexer
        self.policy = policy or DeveloperPolicy()

    @classmethod
    def infer_action(cls, objective: str) -> DeveloperAction:
        lowered = objective.lower()
        for action in (DeveloperAction.PATCH, DeveloperAction.TEST, DeveloperAction.DIAGNOSE):
            if any(hint in lowered for hint in cls._ACTION_HINTS[action]): return action
        return DeveloperAction.INSPECT

    def prepare(self, task: Task, *, query: str | None = None, top_k: int = 8) -> DeveloperContext:
        if task.workspace_id is not None and self.indexer.workspace_id not in (None, task.workspace_id): raise ValueError("code index belongs to a different workspace")
        if not self.indexer.files(): self.indexer.build()
        matches = self.indexer.search(query or task.objective, top_k=top_k)
        return DeveloperContext(self.infer_action(task.objective), task.objective, task.workspace_id, self.indexer.summary(), matches)

    def diagnose(self, failure: str, *, top_k: int = 5) -> DeveloperDiagnostic:
        if not self.indexer.files(): self.indexer.build()
        symptom_match = self._ERROR_RE.search(failure.strip())
        symptom = symptom_match.group(0).strip() if symptom_match else failure.strip()[:240]
        query_terms = re.findall(r"[A-Za-z_][A-Za-z0-9_.:/-]{2,}", failure)
        query = " ".join(dict.fromkeys(query_terms[-8:]))
        matches = self.indexer.search(query, top_k=top_k) if query else ()
        evidence = tuple(f"{match.file.path}: matched {', '.join(match.matches)} (score={match.score:.2f})" for match in matches)
        confidence = min(1.0, 0.25 + 0.15 * len(matches)) if matches else 0.0
        return DeveloperDiagnostic(symptom, tuple(match.file.path for match in matches), evidence, round(confidence, 2))

    def plan_patch(self, task: Task, *, query: str | None = None, depth: int = 1, top_k: int = 5) -> DeveloperPatchPlan:
        context = self.prepare(task, query=query, top_k=top_k)
        targets = tuple(match.file.path for match in context.matches)
        dependencies: list[str] = []
        for target in targets:
            for neighbor in self.indexer.dependency_neighbors(target, depth=depth):
                if neighbor not in targets and neighbor not in dependencies: dependencies.append(neighbor)
        return DeveloperPatchPlan(task.objective, targets, tuple(sorted(dependencies)), ("Inspect the highest-ranked source matches and their local dependency neighborhood.", "Identify the smallest source change that satisfies the objective without touching unrelated files.", "Keep the patch reviewable and do not modify secrets or ignored workspace files."), ("Run the focused regression tests for the changed behavior.", "Run the broader API test suite before merging."), round(min(1.0, 0.35 + 0.12 * len(targets) + 0.05 * len(dependencies)), 2))

    @staticmethod
    def _patch_fingerprint(files: tuple[str, ...], additions: int, deletions: int, risk: str, diff: str) -> str:
        payload = f"NEXUS-PATCH-AUDIT-V2\n{'|'.join(files)}\n{additions}\n{deletions}\n{risk}\n{diff}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def verify_patch_audit(cls, artifact: DeveloperPatchArtifact) -> bool:
        """Verify that audit metadata still describes the exact immutable patch artifact."""
        if artifact.policy is None or artifact.audit is None:
            return False
        audit = artifact.audit
        policy = artifact.policy
        files = tuple(sorted(artifact.files))
        expected = cls._patch_fingerprint(files, artifact.additions, artifact.deletions, policy.risk.value, artifact.diff)
        return (files == artifact.files and audit.schema_version == cls.AUDIT_SCHEMA_VERSION and audit.file_count == len(files) and audit.changed_lines == artifact.additions + artifact.deletions and audit.risk == policy.risk.value and audit.allowed == policy.allowed and audit.requires_approval == policy.requires_approval and audit.fingerprint == expected)

    def build_patch_artifact(self, changes: dict[str, tuple[str, str]], *, context_lines: int = 3, approved: bool = False) -> DeveloperPatchArtifact:
        if context_lines < 0 or context_lines > 20: raise ValueError("context_lines must be between 0 and 20")
        import difflib
        chunks: list[str] = []
        additions = deletions = 0
        for path in sorted(changes):
            if not path or not self._SAFE_PATH_RE.fullmatch(path) or path.startswith("/") or ".." in Path(path).parts: raise ValueError(f"unsafe patch path: {path}")
            before, after = changes[path]
            diff = list(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}", n=context_lines))
            additions += sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
            deletions += sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
            if diff: chunks.append("".join(diff))
        files = tuple(sorted(changes))
        patch_diff = "\n".join(chunks)
        policy = self.policy.evaluate(files, additions=additions, deletions=deletions, approved=approved, added_content=patch_diff)
        if not policy.allowed: raise ValueError(f"developer patch rejected: {policy.reasons[0] if policy.reasons else 'developer patch rejected by policy'}")
        fingerprint = self._patch_fingerprint(files, additions, deletions, policy.risk.value, patch_diff)
        audit = DeveloperPatchAudit(fingerprint, len(files), additions + deletions, policy.risk.value, policy.allowed, policy.requires_approval)
        return DeveloperPatchArtifact(files, patch_diff, additions, deletions, policy, audit)

    @classmethod
    def authorize_patch_execution(cls, artifact: DeveloperPatchArtifact, *, approval: DeveloperApproval | None = None) -> bool:
        """Enforce the final execution boundary against the exact audited patch."""
        if not cls.verify_patch_audit(artifact): return False
        if artifact.policy is None or artifact.audit is None or not artifact.policy.allowed or not artifact.audit.allowed: return False
        if artifact.policy.risk is not PatchRisk.HIGH: return True
        return approval is not None and approval.is_approved and approval.is_time_valid() and approval.is_fresh(max_age_seconds=cls.APPROVAL_MAX_AGE_SECONDS) and approval.matches(artifact.audit.fingerprint)

    def build_verification_plan(self, patch: DeveloperPatchPlan) -> DeveloperVerificationPlan:
        focused = full = "PYTHONPATH=. pytest -q"
        return DeveloperVerificationPlan(focused, full, (f"Focused validation covers the changed behavior in {len(patch.target_files)} target file(s).", "Full validation reuses the repository API suite defined by CI.", "Commands are returned for review; this method does not execute shell commands."))

    def analyze_impact(self, changed_files: tuple[str, ...], *, depth: int = 1) -> DeveloperImpactReport:
        if depth < 1: raise ValueError("depth must be at least 1")
        normalized = tuple(sorted(dict.fromkeys(changed_files)))
        reverse: dict[str, set[str]] = {}
        for edge in self.indexer.dependencies(): reverse.setdefault(edge.target, set()).add(edge.source)
        seen = set(normalized); frontier = set(normalized)
        for _ in range(depth):
            next_frontier: set[str] = set()
            for current in frontier: next_frontier.update(reverse.get(current, set()) - seen)
            seen.update(next_frontier); frontier = next_frontier
            if not frontier: break
        affected = tuple(sorted(seen - set(normalized)))
        evidence = tuple(f"{changed}: downstream local files include {', '.join(sorted(reverse.get(changed, set())))}" for changed in normalized if reverse.get(changed))
        return DeveloperImpactReport(normalized, affected, len(affected), evidence)

    @staticmethod
    def verification_result(command: str, *, exit_code: int | None, output: str) -> DeveloperVerificationResult:
        if not command.strip(): raise ValueError("command must not be empty")
        status = "not_run" if exit_code is None else "passed" if exit_code == 0 else "failed"
        evidence = ("Verification status is derived solely from the supplied exit code.", "Command output is preserved as evidence; no command is executed here.")
        return DeveloperVerificationResult(command.strip(), status, exit_code, output, evidence)
