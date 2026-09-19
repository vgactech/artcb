"""LLM enrichment — rule-based + connecteurs utilisateur (OpenAI, Claude, Bob)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import TYPE_CHECKING

from src.artcb.ir.bob_client import BobClient
from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.grammar import NodeType
from src.artcb.ir.models import IRGraph

if TYPE_CHECKING:
    from src.artcb.connectors.manager import ConnectorManager

logger = logging.getLogger("artcb.ir.llm_encoder")


class LLMEncoder:
    """Wraps rule-based encoder; enrichit via LLM connecté par l'utilisateur."""

    def __init__(
        self,
        encoder: IREncoder | None = None,
        bob: BobClient | None = None,
        connectors: ConnectorManager | None = None,
    ) -> None:
        self.encoder = encoder or IREncoder()
        self.bob = bob or BobClient()
        self.connectors = connectors

    def encode(
        self,
        text: str,
        *,
        use_llm: bool = False,
        session_id: str | None = None,
        llm_provider: str | None = None,
    ) -> IRGraph:
        graph = self.encoder.encode(text, session_id=session_id)
        if not use_llm:
            return graph

        sentences = [node.txt for node in graph.nodes]
        classifications = self._classify(sentences, llm_provider=llm_provider)
        if not classifications:
            logger.debug("LLM enrichment skipped — rule-based graph returned")
            return graph

        type_map = {member.value: member for member in NodeType}
        nodes = list(graph.nodes)
        for item in classifications:
            try:
                idx = int(item["index"])
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(nodes):
                continue
            node = nodes[idx]
            node_type = type_map.get(item["type"].upper(), NodeType.FACT)
            symbol = item.get("symbol") or node.sym
            nodes[idx] = node.model_copy(update={"t": node_type.value, "sym": symbol})

        enriched = graph.model_copy(update={"nodes": nodes})
        logger.debug("LLM enrichment applied nodes=%d provider=%s", len(nodes), llm_provider)
        return enriched

    def _classify(self, sentences: list[str], *, llm_provider: str | None) -> list[dict[str, str]] | None:
        if llm_provider and self.connectors:
            from src.artcb.connectors.llm_router import LLMRouter

            active = self.connectors.get_active_llm_key(llm_provider)
            if active:
                record, api_key = active
                return LLMRouter().classify_sentences(sentences, record=record, api_key=api_key)
            logger.warning("No connector for provider %s — fallback Bob/.env", llm_provider)

        return self.bob.classify_sentences(sentences)
