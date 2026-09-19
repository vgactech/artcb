"""B-Tree-like node indexing for fast lookups (Optimisation #7)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.artcb.ir.models import IRGraph, IRNode

logger = logging.getLogger("artcb.memory.node_index")


class NodeIndex:
    """Fast node lookup using sorted index (B-Tree-like structure)."""

    def __init__(self) -> None:
        """Initialize node index."""
        # Sorted list of (node_id, graph_id, node) tuples
        self._index: list[tuple[str, str, IRNode]] = []
        self._sorted = True

        # Secondary indices for common queries
        self._by_type: dict[str, list[tuple[str, str, IRNode]]] = {}
        self._by_symbol: dict[str, list[tuple[str, str, IRNode]]] = {}

        # Statistics
        self._total_nodes = 0

    def add_graph(self, graph: IRGraph) -> None:
        """Add all nodes from a graph to the index.

        Args:
            graph: IR graph to index
        """
        for node in graph.nodes:
            entry = (node.id, graph.graph_id, node)
            self._index.append(entry)

            # Add to type index
            if node.t not in self._by_type:
                self._by_type[node.t] = []
            self._by_type[node.t].append(entry)

            # Add to symbol index
            if node.sym not in self._by_symbol:
                self._by_symbol[node.sym] = []
            self._by_symbol[node.sym].append(entry)

            self._total_nodes += 1

        self._sorted = False
        logger.debug(
            "Indexed graph_id=%s nodes=%d total=%d",
            graph.graph_id,
            len(graph.nodes),
            self._total_nodes,
        )

    def _ensure_sorted(self) -> None:
        """Ensure main index is sorted for binary search."""
        if not self._sorted:
            self._index.sort(key=lambda x: x[0])
            self._sorted = True

    def find_by_id(self, node_id: str) -> tuple[str, IRNode] | None:
        """Find node by ID using binary search.

        Args:
            node_id: Node ID to search for

        Returns:
            Tuple of (graph_id, node) or None if not found
        """
        self._ensure_sorted()

        # Binary search - compare only node_id (first element of tuple)
        # Find insertion point
        left, right = 0, len(self._index)
        while left < right:
            mid = (left + right) // 2
            if self._index[mid][0] < node_id:
                left = mid + 1
            else:
                right = mid

        # Check if found
        if left < len(self._index) and self._index[left][0] == node_id:
            node_id_found, graph_id, node = self._index[left]
            return (graph_id, node)

        return None

    def find_by_type(self, node_type: str, limit: int = 100) -> list[tuple[str, IRNode]]:
        """Find nodes by type.

        Args:
            node_type: Node type to search for
            limit: Maximum number of results

        Returns:
            List of (graph_id, node) tuples
        """
        if node_type not in self._by_type:
            return []

        entries = self._by_type[node_type][:limit]
        return [(graph_id, node) for _, graph_id, node in entries]

    def find_by_symbol(self, symbol: str, limit: int = 100) -> list[tuple[str, IRNode]]:
        """Find nodes by symbol.

        Args:
            symbol: Symbol to search for
            limit: Maximum number of results

        Returns:
            List of (graph_id, node) tuples
        """
        if symbol not in self._by_symbol:
            return []

        entries = self._by_symbol[symbol][:limit]
        return [(graph_id, node) for _, graph_id, node in entries]

    def find_by_text_prefix(self, prefix: str, limit: int = 100) -> list[tuple[str, IRNode]]:
        """Find nodes by text prefix (case-insensitive).

        Args:
            prefix: Text prefix to search for
            limit: Maximum number of results

        Returns:
            List of (graph_id, node) tuples
        """
        prefix_lower = prefix.lower()
        results = []

        for _, graph_id, node in self._index:
            if node.txt.lower().startswith(prefix_lower):
                results.append((graph_id, node))
                if len(results) >= limit:
                    break

        return results

    def get_stats(self) -> dict:
        """Get index statistics.

        Returns:
            Dictionary with index statistics
        """
        return {
            "total_nodes": self._total_nodes,
            "unique_types": len(self._by_type),
            "unique_symbols": len(self._by_symbol),
            "sorted": self._sorted,
        }

    def clear(self) -> None:
        """Clear all indices."""
        self._index.clear()
        self._by_type.clear()
        self._by_symbol.clear()
        self._total_nodes = 0
        self._sorted = True
        logger.debug("NodeIndex cleared")

    def __len__(self) -> int:
        """Return total number of indexed nodes."""
        return self._total_nodes

