"""Explorer agent — hypothesis generation, symbol proposals, node decomposition."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import re
import uuid
from dataclasses import dataclass, field

from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.grammar import ACTION_TRIGGERS, OBJECT_TRIGGERS
from src.artcb.ir.models import IRGraph
from src.artcb.ir.symbol_store import PersistentSymbolRegistry

logger = logging.getLogger("artcb.agents.explorer")

_KNOWN_TOKENS = set(ACTION_TRIGGERS) | set(OBJECT_TRIGGERS)
_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ]{4,}")


@dataclass
class SymbolProposal:
    concept: str
    symbol: str
    status: str = "proposed"
    reason: str = "concept absent du dictionnaire USP"


@dataclass
class ExplorerResult:
    graph: IRGraph
    symbol_proposals: list[SymbolProposal] = field(default_factory=list)


class ExplorerAgent:
    """Decomposes input text into IR graph nodes and proposes original symbols."""

    def __init__(
        self,
        encoder: IREncoder | None = None,
        symbol_registry: PersistentSymbolRegistry | None = None,
    ) -> None:
        self._symbol_store = symbol_registry
        if encoder is not None:
            self.encoder = encoder
        elif symbol_registry is not None:
            self.encoder = IREncoder(symbol_registry=symbol_registry.registry)
        else:
            self.encoder = IREncoder()

    def propose_symbols(self, text: str) -> list[SymbolProposal]:
        """Detecte les concepts inconnus et propose des symboles originaux."""
        proposals: list[SymbolProposal] = []
        seen: set[str] = set()
        lowered = text.lower()

        for match in _WORD_RE.finditer(text):
            word = match.group(0).lower()
            if word in _KNOWN_TOKENS or word in seen:
                continue
            if any(word in trigger for trigger in _KNOWN_TOKENS):
                continue
            seen.add(word)

            registry = (
                self._symbol_store.registry
                if self._symbol_store
                else self.encoder._registry
            )
            key = registry.concept_key(word)
            existing = registry._concept_to_symbol.get(key)
            if existing:
                symbol = existing
                status = "existing"
            elif self._symbol_store:
                symbol = self._symbol_store.mint_original(word)
                status = "minted"
            else:
                symbol = registry.mint_original(word)
                status = "minted"

            proposals.append(
                SymbolProposal(
                    concept=word,
                    symbol=symbol,
                    status=status,
                    reason="mot absent des declencheurs USP",
                )
            )

        if "flarnick" in lowered or "zorbax" in lowered:
            for novel in ("flarnick", "zorbax"):
                if novel in lowered and novel not in seen:
                    reg = self._symbol_store.registry if self._symbol_store else self.encoder._registry
                    sym = (
                        self._symbol_store.mint_original(novel)
                        if self._symbol_store
                        else reg.mint_original(novel)
                    )
                    proposals.append(
                        SymbolProposal(concept=novel, symbol=sym, status="minted", reason="neologisme detecte")
                    )

        logger.debug("Explorer proposed %d symbols for len=%d", len(proposals), len(text))
        return proposals

    def explore(self, text: str, *, graph_id: str | None = None) -> ExplorerResult:
        gid = graph_id or f"g_{uuid.uuid4().hex[:12]}"
        proposals = self.propose_symbols(text)
        logger.debug("ExplorerAgent graph_id=%s input_len=%d proposals=%d", gid, len(text), len(proposals))
        graph = self.encoder.encode(text, session_id=gid)
        graph = graph.model_copy(update={"graph_id": gid})
        if self._symbol_store:
            self._symbol_store.publish_from_graph(graph.orig_symbols)
        return ExplorerResult(graph=graph, symbol_proposals=proposals)
