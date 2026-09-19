"""Semantic search over IR node text (MVP — keyword + similarity)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from difflib import SequenceMatcher

from src.artcb.ir.models import IRGraph, IRNode

logger = logging.getLogger("artcb.memory.vector_store")


class VectorStore:
    """In-memory semantic search without external embedding model (CDC §3.2.6 MVP)."""

    def __init__(self) -> None:
        self._entries: dict[str, list[tuple[str, IRNode]]] = {}

    def index_graph(self, graph: IRGraph) -> None:
        self._entries[graph.graph_id] = [(graph.graph_id, node) for node in graph.nodes]
        logger.debug("Indexed graph_id=%s nodes=%d", graph.graph_id, len(graph.nodes))

    @staticmethod
    def _score(query: str, text: str) -> float:
        q = query.lower().strip()
        t = text.lower()
        if q in t:
            return 1.0
        return SequenceMatcher(None, q, t).ratio()

    def search(self, query: str, graph_id: str | None = None, top_k: int = 3) -> list[dict]:
        results: list[tuple[float, IRNode, str]] = []
        graphs = (
            {graph_id: self._entries[graph_id]}
            if graph_id and graph_id in self._entries
            else self._entries
        )
        for gid, nodes in graphs.items():
            for _, node in nodes:
                score = self._score(query, node.txt)
                if score > 0.15:
                    results.append((score, node, gid))

        results.sort(key=lambda item: item[0], reverse=True)
        top = results[:top_k]
        return [
            {
                "graph_id": gid,
                "node_id": node.id,
                "score": round(score, 4),
                "text": node.txt,
                "type": node.t,
                "symbol": node.sym,
            }
            for score, node, gid in top
        ]
