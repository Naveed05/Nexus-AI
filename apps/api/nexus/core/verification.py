import re
from dataclasses import dataclass
from typing import Any

from nexus.core.task import Task


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True)
class GroundingAssessment:
    citation: str
    claim: str
    evidence: str
    overlap_score: float
    supported: bool


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: dict[str, bool]
    issues: tuple[str, ...] = ()
    grounding: tuple[GroundingAssessment, ...] = ()


class OutputVerifier:
    """Deterministic verifier for observable execution and research-grounding properties."""

    _citation_pattern = re.compile(r"\[Source:\s*([^\]]+)\]")
    _token_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}")
    _stopwords = {
        "about", "after", "also", "among", "because", "being", "could", "from",
        "have", "into", "more", "that", "their", "there", "these", "they", "this",
        "through", "using", "were", "which", "with", "would", "your", "than", "then",
    }

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        return {
            token.lower()
            for token in cls._token_pattern.findall(text)
            if token.lower() not in cls._stopwords
        }

    @classmethod
    def _match_claim_to_evidence(cls, claim: str, evidence: str) -> float:
        claim_tokens = cls._tokens(claim)
        evidence_tokens = cls._tokens(evidence)
        if not claim_tokens or not evidence_tokens:
            return 0.0
        return len(claim_tokens & evidence_tokens) / len(claim_tokens)

    @classmethod
    def _assess_grounding(
        cls,
        output: str,
        grounded_evidence: tuple[dict[str, Any], ...],
    ) -> tuple[GroundingAssessment, ...]:
        available = {
            str(item.get("citation")).strip(): str(item.get("text") or "").strip()
            for item in grounded_evidence
            if item.get("citation") and item.get("text")
        }
        assessments: list[GroundingAssessment] = []
        for paragraph in re.split(r"\n+", output):
            citations = cls._citation_pattern.findall(paragraph)
            if not citations:
                continue
            claim = cls._citation_pattern.sub("", paragraph).strip(" -:;\t")
            for citation in citations:
                citation = citation.strip()
                evidence = available.get(citation, "")
                overlap = cls._match_claim_to_evidence(claim, evidence) if evidence else 0.0
                # A cited claim needs either two meaningful shared terms or at least 25% coverage.
                claim_tokens = cls._tokens(claim)
                shared = len(cls._tokens(claim) & cls._tokens(evidence)) if evidence else 0
                supported = bool(evidence) and (shared >= 2 or overlap >= 0.25)
                assessments.append(
                    GroundingAssessment(
                        citation=citation,
                        claim=claim,
                        evidence=evidence,
                        overlap_score=round(overlap, 3),
                        supported=supported,
                    )
                )
        return tuple(assessments)

    @staticmethod
    def _is_research_task(
        task: Task,
        tool_calls: tuple[Any, ...],
        grounded_evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        capabilities = {capability.lower() for capability in task.capabilities}
        return (
            bool(capabilities.intersection({"research", "synthesize"}))
            or bool(grounded_evidence)
            or any(getattr(call, "tool_name", "") == "search_knowledge" for call in tool_calls)
        )

    def _verify_grounding(
        self,
        task: Task,
        output: str,
        tool_calls: tuple[Any, ...],
        grounded_evidence: tuple[dict[str, Any], ...],
    ) -> tuple[bool, str, tuple[GroundingAssessment, ...]]:
        if not self._is_research_task(task, tool_calls, grounded_evidence):
            return True, "Grounding check not required for this task.", ()

        if not grounded_evidence:
            return False, "Research task produced no retrieved evidence.", ()

        citations = self._citation_pattern.findall(output)
        if not citations:
            return False, "Research output does not contain a citation to retrieved evidence.", ()

        available = {
            str(item.get("citation")).strip()
            for item in grounded_evidence
            if item.get("citation")
        }
        unsupported = [citation.strip() for citation in citations if citation.strip() not in available]
        if unsupported:
            return False, f"Research output contains unsupported citations: {', '.join(unsupported)}", ()

        assessments = self._assess_grounding(output, grounded_evidence)
        unsupported_claims = [item for item in assessments if not item.supported]
        if unsupported_claims:
            citations_text = ", ".join(item.citation for item in unsupported_claims)
            return False, f"Research output contains claims not supported by cited evidence: {citations_text}", assessments

        return True, "Research output cites retrieved evidence and claims match the cited evidence.", assessments

    def verify(
        self,
        task: Task,
        output: str,
        tool_calls: tuple[Any, ...] = (),
        grounded_evidence: tuple[dict[str, Any], ...] = (),
    ) -> VerificationResult:
        objective_present = bool(task.objective.strip())
        output_present = bool(output.strip())
        tools_recorded = all(bool(getattr(call, "tool_name", "")) for call in tool_calls)
        grounding_passed, grounding_message, grounding = self._verify_grounding(
            task,
            output,
            tool_calls,
            grounded_evidence,
        )
        checks = {
            "non_empty_output": output_present,
            "objective_present": objective_present,
            "tool_calls_recorded": tools_recorded,
            "grounded_research": grounding_passed,
        }
        messages = {
            "non_empty_output": "Output is non-empty." if output_present else "Model returned empty output.",
            "objective_present": "Task objective is present." if objective_present else "Task objective is empty.",
            "tool_calls_recorded": "Tool calls are recorded correctly." if tools_recorded else "A tool call is missing its name.",
            "grounded_research": grounding_message,
        }
        return VerificationResult(
            passed=all(checks.values()),
            checks=checks,
            issues=tuple(messages[name] for name, passed in checks.items() if not passed),
            grounding=grounding,
        )
