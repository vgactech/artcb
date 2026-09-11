"""Original symbol registry — AI-minted symbols for ARTCB language."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

ORIGIN_ALPHABET = list("αβγδεζηθικλμνξοπρστυφχψω")
ORIGIN_PREFIX = "∇"


@dataclass
class SymbolRegistry:
    """Mints unique original symbols for concepts not in the fixed USP dictionary."""

    _concept_to_symbol: dict[str, str] = field(default_factory=dict)
    _symbol_counter: int = 1

    def normalize_concept(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.lower().strip())
        return cleaned[:120]

    def concept_key(self, text: str) -> str:
        normalized = self.normalize_concept(text)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return f"{normalized}|{digest}"

    def mint_original(self, concept: str) -> str:
        """Return a stable original symbol for a novel concept.

        R325 2026-09-12T01:45:00Z — symbol embeds content digest so ConceptID
        differs across distinct unknown texts. ~~counter-only α1/β2~~ barred:
        every fresh IREncoder minted ``α1`` for the first unknown → cross-run
        ConceptID collision (R325 publisher-death cold falsely non-empty).
        Counter greek form kept only as secondary disambiguator inside one registry.
        """
        key = self.concept_key(concept)
        if key in self._concept_to_symbol:
            return self._concept_to_symbol[key]

        digest = key.rsplit("|", 1)[-1]
        index = self._symbol_counter
        self._symbol_counter += 1
        # Content-addressed original — stable across process restarts for same text.
        symbol = f"{ORIGIN_PREFIX}{digest[:12]}"
        # Keep legacy counter mapping exportable for debugging (not used in ConceptID path alone).
        _ = index  # reserved; do not restore α1-only mint
        self._concept_to_symbol[key] = symbol
        return symbol

    def is_original(self, symbol: str) -> bool:
        return symbol.startswith(ORIGIN_PREFIX) or (
            len(symbol) >= 2 and symbol[0] in ORIGIN_ALPHABET
        )

    def export(self) -> dict[str, str]:
        return dict(self._concept_to_symbol)

    @classmethod
    def from_export(cls, data: dict[str, str]) -> SymbolRegistry:
        registry = cls()
        registry._concept_to_symbol = dict(data)
        if data:
            registry._symbol_counter = len(data) + 1
        return registry
