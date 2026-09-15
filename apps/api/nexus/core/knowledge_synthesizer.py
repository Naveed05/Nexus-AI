from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeSynthesis:
    """Deterministic synthesis of bounded evidence into reusable knowledge."""

    summary: str
    themes: tuple[str, ...]
    evidence: tuple[str, ...]
    contradictions: tuple[str, ...]
    confidence: float


class KnowledgeSynthesizer:
    """Combine memory/evidence items without inventing facts or executing tools."""

    def synthesize(self, items: tuple[str, ...] | list[str], *, query: str = "") -> KnowledgeSynthesis:
        cleaned = tuple(dict.fromkeys(item.strip() for item in items if item and item.strip()))
        if not cleaned:
            return KnowledgeSynthesis("No evidence available.", (), (), (), 0.0)

        words: dict[str, int] = {}
        for item in cleaned:
            for word in item.lower().replace("\n", " ").split():
                token = "".join(ch for ch in word if ch.isalnum())
                if len(token) >= 5:
                    words[token] = words.get(token, 0) + 1
        themes = tuple(word for word, count in sorted(words.items(), key=lambda pair: (-pair[1], pair[0])) if count > 1)[:5]

        contradictions = tuple(
            f"conflicting evidence: {cleaned[index]} | {cleaned[index + 1]}"
            for index in range(len(cleaned) - 1)
            if {"not", "never"} & set(cleaned[index].lower().split())
            and {"not", "never"} & set(cleaned[index + 1].lower().split())
        )[:3]
        confidence = min(1.0, 0.35 + 0.1 * len(cleaned) + 0.05 * len(themes) - 0.1 * len(contradictions))
        prefix = f"Synthesis for {query.strip()}: " if query.strip() else "Synthesis: "
        summary = prefix + " ".join(cleaned[:3])
        return KnowledgeSynthesis(summary, themes, cleaned, contradictions, round(max(0.0, confidence), 3))
