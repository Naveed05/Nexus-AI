from __future__ import annotations

from dataclasses import dataclass

from nexus.core.knowledge_synthesizer import KnowledgeSynthesis, KnowledgeSynthesizer


@dataclass(frozen=True)
class CrossMemoryReasoning:
    """Structured conclusions derived from multiple memory/evidence sources."""

    conclusion: str
    supporting_items: tuple[str, ...]
    gaps: tuple[str, ...]
    confidence: float


class CrossMemoryReasoner:
    """Perform bounded cross-memory reasoning while preserving source traceability."""

    def __init__(self, synthesizer: KnowledgeSynthesizer | None = None) -> None:
        self._synthesizer = synthesizer or KnowledgeSynthesizer()

    def reason(self, memories: tuple[str, ...] | list[str], *, query: str = "") -> CrossMemoryReasoning:
        synthesis: KnowledgeSynthesis = self._synthesizer.synthesize(memories, query=query)
        if not synthesis.evidence:
            return CrossMemoryReasoning("Insufficient evidence to reason across memory.", (), ("missing evidence",), 0.0)

        gaps: list[str] = []
        if synthesis.confidence < 0.6:
            gaps.append("low evidence confidence")
        if synthesis.contradictions:
            gaps.append("resolve contradictory memories")
        if query.strip() and not any(query.lower().split() and token in synthesis.summary.lower() for token in query.lower().split()):
            gaps.append("query alignment is weak")

        conclusion = synthesis.summary
        if synthesis.themes:
            conclusion += " Themes: " + ", ".join(synthesis.themes) + "."
        return CrossMemoryReasoning(
            conclusion=conclusion,
            supporting_items=synthesis.evidence,
            gaps=tuple(gaps),
            confidence=max(0.0, round(synthesis.confidence - 0.05 * len(gaps), 3)),
        )
