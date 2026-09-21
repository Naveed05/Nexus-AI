from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class ConflictResolution(str, Enum):
    ACCEPT = "accept"
    MERGE = "merge"
    ESCALATE = "escalate"

@dataclass(frozen=True)
class AgentProposal:
    agent_id: str
    claim: str
    evidence: tuple[str, ...] = ()
    confidence: float = 0.0
    def __post_init__(self) -> None:
        if not self.agent_id.strip() or not self.claim.strip(): raise ValueError("agent_id and claim cannot be empty")
        if not 0.0 <= self.confidence <= 1.0: raise ValueError("confidence must be between 0 and 1")

@dataclass(frozen=True)
class ConflictResult:
    resolution: ConflictResolution
    selected_agent: str | None
    rationale: str

class ConflictResolver:
    """Deterministic conflict policy: evidence first, confidence second, escalation on ties."""
    def __init__(self, confidence_gap: float = 0.10) -> None:
        if confidence_gap < 0: raise ValueError("confidence_gap cannot be negative")
        self.confidence_gap = confidence_gap

    def resolve(self, proposals: tuple[AgentProposal, ...]) -> ConflictResult:
        if not proposals: raise ValueError("at least one proposal is required")
        if len(proposals) == 1: return ConflictResult(ConflictResolution.ACCEPT, proposals[0].agent_id, "single proposal")
        ordered = sorted(proposals, key=lambda x: (bool(x.evidence), x.confidence), reverse=True)
        top, second = ordered[0], ordered[1]
        if top.claim == second.claim: return ConflictResult(ConflictResolution.MERGE, None, "proposals agree on the claim")
        if bool(top.evidence) and top.confidence - second.confidence >= self.confidence_gap:
            return ConflictResult(ConflictResolution.ACCEPT, top.agent_id, "evidence-backed proposal clears confidence gap")
        return ConflictResult(ConflictResolution.ESCALATE, None, "conflicting proposals lack a decisive evidence/confidence margin")
