"""Critic agent — validation, compression review, PoL computation."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging

from src.artcb.agents.explorer import ExplorerAgent, ExplorerResult
from src.artcb.ir.decoder import IRDecoder
from src.artcb.ir.models import IRGraph, sha256_text
from src.artcb.pol.scorer import PolMetrics, PolScorer

logger = logging.getLogger("artcb.agents.critic")


class CriticResult:
    def __init__(
        self,
        graph: IRGraph,
        pol: PolMetrics,
        nodes_validated: int,
        nodes_proposed: int,
        symbol_proposals: list | None = None,
    ) -> None:
        self.graph = graph
        self.pol = pol
        self.nodes_validated = nodes_validated
        self.nodes_proposed = nodes_proposed
        self.symbol_proposals = symbol_proposals or []


class CriticAgent:
    """Validates nodes, verifies reversibility, computes PoL."""

    def __init__(
        self,
        scorer: PolScorer | None = None,
        decoder: IRDecoder | None = None,
    ) -> None:
        self.scorer = scorer or PolScorer()
        self.decoder = decoder or IRDecoder()

    def validate(self, graph: IRGraph) -> CriticResult:
        nodes_proposed = len(graph.nodes)
        nodes_validated = 0

        for node in graph.nodes:
            expected = sha256_text(node.txt)
            if node.checksum == expected and node.txt.strip():
                nodes_validated += 1
            else:
                logger.warning("Critic rejected node_id=%s bad_checksum", node.id)

        decode_metrics = self.decoder.decode_with_metrics(graph)
        nodes_correct = nodes_validated if decode_metrics["reversible"] else 0

        pol = self.scorer.score(
            graph,
            nodes_validated=nodes_validated,
            nodes_proposed=nodes_proposed,
            nodes_retrieved=nodes_proposed,
            nodes_correct=nodes_correct,
        )

        logger.debug(
            "CriticAgent pol=%.4f validated=%d/%d accepted=%s",
            pol.pol_score,
            nodes_validated,
            nodes_proposed,
            pol.block_accepted,
        )

        return CriticResult(
            graph=graph,
            pol=pol,
            nodes_validated=nodes_validated,
            nodes_proposed=nodes_proposed,
        )


class DualAgentLoop:
    """Explorer → Critic pipeline (CDC §3.2.3)."""

    def __init__(
        self,
        explorer: ExplorerAgent | None = None,
        critic: CriticAgent | None = None,
    ) -> None:
        self.explorer = explorer or ExplorerAgent()
        self.critic = critic or CriticAgent()

    def run(self, text: str, *, graph_id: str | None = None) -> CriticResult:
        explored: ExplorerResult = self.explorer.explore(text, graph_id=graph_id)
        result = self.critic.validate(explored.graph)
        result.symbol_proposals = explored.symbol_proposals
        return result
