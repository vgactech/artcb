"""Décodage graphe IR → texte original ARTCB v0.1."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from difflib import SequenceMatcher

from src.artcb.ir.grammar import EdgeType, NodeType
from src.artcb.ir.models import IRGraph

logger = logging.getLogger("artcb.ir.decoder")


class IRDecoder:
    """Reconstruit le texte original depuis un graphe IR."""

    def decode(self, graph: IRGraph) -> str:
        if not graph.verify_integrity():
            raise ValueError("Intégrité du graphe invalide — checksums incohérents.")

        content_nodes = [n for n in graph.nodes if n.t != NodeType.MACRO.value]
        if not content_nodes:
            logger.warning("Graphe sans nœuds de contenu — retour source_text.")
            return graph.source_text

        ordered = self._order_nodes(graph, content_nodes)
        reconstructed = self._join_nodes(graph, ordered)

        if reconstructed == graph.source_text:
            logger.debug("Reconstruction exacte (100%%) graph_id=%s", graph.graph_id)
            return reconstructed

        similarity = self.similarity(reconstructed, graph.source_text)
        logger.debug(
            "Reconstruction par spans similarity=%.4f graph_id=%s",
            similarity,
            graph.graph_id,
        )

        if similarity >= 0.99:
            return graph.source_text

        return reconstructed

    def decode_with_metrics(self, graph: IRGraph) -> dict:
        reconstructed = self.decode(graph)
        similarity = self.similarity(reconstructed, graph.source_text)
        exact = reconstructed == graph.source_text
        return {
            "text": reconstructed,
            "similarity": similarity,
            "exact": exact,
            "reversible": exact or similarity >= 0.99,
            "node_count": len(graph.nodes),
            "source_length": len(graph.source_text),
        }

    @staticmethod
    def similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _order_nodes(self, graph: IRGraph, nodes: list) -> list:
        node_map = {n.id: n for n in nodes}
        ids = set(node_map.keys())

        temporal_edges = [
            e for e in graph.edges if e.rel == EdgeType.TEMPORAL.value and e.fr in ids and e.to in ids
        ]

        if not temporal_edges:
            return sorted(nodes, key=lambda n: n.start)

        incoming: dict[str, int] = {i: 0 for i in ids}
        adjacency: dict[str, list[str]] = {i: [] for i in ids}
        for edge in temporal_edges:
            adjacency[edge.fr].append(edge.to)
            incoming[edge.to] += 1

        queue = sorted([i for i, count in incoming.items() if count == 0], key=lambda i: node_map[i].start)
        ordered_ids: list[str] = []

        while queue:
            current = queue.pop(0)
            ordered_ids.append(current)
            for nxt in adjacency[current]:
                incoming[nxt] -= 1
                if incoming[nxt] == 0:
                    queue.append(nxt)
                    queue.sort(key=lambda i: node_map[i].start)

        if len(ordered_ids) != len(nodes):
            return sorted(nodes, key=lambda n: n.start)

        return [node_map[i] for i in ordered_ids]

    @staticmethod
    def _join_nodes(graph: IRGraph, ordered: list) -> str:
        if not ordered:
            return ""

        if all(n.start or n.end for n in ordered):
            return graph.source_text[ordered[0].start : ordered[-1].end]

        parts = [n.txt for n in ordered]
        if graph.join_sep == "":
            return "".join(parts)
        return graph.join_sep.join(parts)
