"""Persist IR graphs to disk."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
from pathlib import Path

from src.artcb.ir.models import IRGraph

logger = logging.getLogger("artcb.memory.graph_store")


class GraphStore:
    def __init__(self, directory: Path, enable_cache: bool = True, max_cache_size: int = 100) -> None:
        """Initialize graph store with optional lazy loading.

        Args:
            directory: Directory to store graphs
            enable_cache: Whether to cache loaded graphs in memory
            max_cache_size: Maximum number of graphs to keep in cache (LRU)
        """
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.enable_cache = enable_cache
        self.max_cache_size = max_cache_size
        self.cache: dict[str, IRGraph] = {}
        self._cache_order: list[str] = []  # LRU tracking

    def _path(self, graph_id: str) -> Path:
        return self.directory / f"{graph_id}.json"

    def save(self, graph: IRGraph) -> None:
        path = self._path(graph.graph_id)
        path.write_text(graph.to_json(), encoding="utf-8")

        if self.enable_cache:
            self._add_to_cache(graph.graph_id, graph)

        logger.debug("Saved graph_id=%s path=%s cached=%s", graph.graph_id, path, self.enable_cache)

    def load(self, graph_id: str) -> IRGraph | None:
        # Check cache first
        if self.enable_cache and graph_id in self.cache:
            self._touch_cache(graph_id)
            logger.debug("Cache HIT graph_id=%s", graph_id)
            return self.cache[graph_id]

        # Load from disk
        path = self._path(graph_id)
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        graph = IRGraph.from_dict(data)

        if self.enable_cache:
            self._add_to_cache(graph_id, graph)

        logger.debug("Loaded graph_id=%s from disk cached=%s", graph_id, self.enable_cache)
        return graph

    def _add_to_cache(self, graph_id: str, graph: IRGraph) -> None:
        """Add graph to cache with LRU eviction."""
        # Remove if already exists (to update order)
        if graph_id in self.cache:
            self._cache_order.remove(graph_id)

        # Add to cache
        self.cache[graph_id] = graph
        self._cache_order.append(graph_id)

        # Evict oldest if cache is full
        while len(self.cache) > self.max_cache_size:
            oldest = self._cache_order.pop(0)
            del self.cache[oldest]
            logger.debug("Evicted graph_id=%s from cache (LRU)", oldest)

    def _touch_cache(self, graph_id: str) -> None:
        """Mark graph as recently used (move to end of LRU list)."""
        if graph_id in self._cache_order:
            self._cache_order.remove(graph_id)
            self._cache_order.append(graph_id)

    def load_all(self) -> list[IRGraph]:
        graphs: list[IRGraph] = []
        for path in self.directory.glob("g_*.json"):
            graph_id = path.stem
            graph = self.load(graph_id)
            if graph:
                graphs.append(graph)
        return graphs
