"""Agent pool manager for parallel processing (Optimisation #5)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import multiprocessing as mp
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import TypeVar

from src.artcb.agents.critic import CriticAgent
from src.artcb.agents.explorer import ExplorerAgent
from src.artcb.ir.models import IRGraph

logger = logging.getLogger("artcb.agents.pool_manager")

T = TypeVar('T')


class AgentPoolManager:
    """Manage parallel agent execution using process/thread pools."""

    def __init__(
        self,
        max_workers: int = 4,
        use_processes: bool = False,
    ) -> None:
        """Initialize agent pool manager.

        Args:
            max_workers: Maximum number of parallel workers
            use_processes: Use ProcessPoolExecutor (True) or ThreadPoolExecutor (False)
        """
        self.max_workers = max_workers
        self.use_processes = use_processes

        if use_processes:
            ctx = mp.get_context("spawn")
            self.executor = ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx)
            logger.info("AgentPoolManager initialized with %d processes (spawn)", max_workers)
        else:
            self.executor = ThreadPoolExecutor(max_workers=max_workers)
            logger.info("AgentPoolManager initialized with %d threads", max_workers)

    def explore_batch(
        self,
        texts: list[str],
        graph_ids: list[str] | None = None,
    ) -> list[IRGraph]:
        """Explore multiple texts in parallel.

        Args:
            texts: List of texts to encode
            graph_ids: Optional list of graph IDs (must match texts length)

        Returns:
            List of IR graphs in same order as input texts
        """
        if graph_ids and len(graph_ids) != len(texts):
            raise ValueError("graph_ids length must match texts length")

        if not graph_ids:
            graph_ids = [None] * len(texts)

        def explore_one(text: str, gid: str | None) -> IRGraph:
            explorer = ExplorerAgent()
            result = explorer.explore(text, graph_id=gid)
            return result.graph

        # Submit all tasks
        futures = []
        for text, gid in zip(texts, graph_ids, strict=False):
            future = self.executor.submit(explore_one, text, gid)
            futures.append(future)

        # Collect results in order
        graphs = []
        for future in futures:
            try:
                graph = future.result(timeout=60)
                graphs.append(graph)
            except Exception as e:
                logger.error("Exploration failed: %s", e)
                raise

        logger.debug("Explored %d texts in parallel", len(graphs))
        return graphs

    def validate_batch(
        self,
        graphs: list[IRGraph],
    ) -> list[dict]:
        """Validate multiple graphs in parallel.

        Args:
            graphs: List of IR graphs to validate

        Returns:
            List of validation results (dicts) in same order as input graphs
        """
        def validate_one(graph: IRGraph) -> dict:
            critic = CriticAgent()
            result = critic.validate(graph)
            # Convert CriticResult to dict
            return {
                "valid": result.nodes_validated > 0,
                "nodes_validated": result.nodes_validated,
                "nodes_proposed": result.nodes_proposed,
                "pol_score": result.pol.pol_score,
                "graph_id": graph.graph_id
            }

        # Submit all tasks
        futures = []
        for graph in graphs:
            future = self.executor.submit(validate_one, graph)
            futures.append(future)

        # Collect results in order
        results = []
        for future in futures:
            try:
                result = future.result(timeout=60)
                results.append(result)
            except Exception as e:
                logger.error("Validation failed: %s", e)
                raise

        logger.debug("Validated %d graphs in parallel", len(results))
        return results

    def map_parallel(
        self,
        func: Callable[[T], T],
        items: list[T],
        timeout: int = 60,
    ) -> list[T]:
        """Map a function over items in parallel.

        Args:
            func: Function to apply to each item
            items: List of items to process
            timeout: Timeout per item in seconds

        Returns:
            List of results in same order as input items
        """
        futures = [self.executor.submit(func, item) for item in items]

        results = []
        for future in futures:
            try:
                result = future.result(timeout=timeout)
                results.append(result)
            except Exception as e:
                logger.error("Parallel map failed: %s", e)
                raise

        return results

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor pool.

        Args:
            wait: Whether to wait for pending tasks to complete
        """
        self.executor.shutdown(wait=wait)
        logger.debug("AgentPoolManager shutdown")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown(wait=True)

