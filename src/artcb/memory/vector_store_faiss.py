"""FAISS-based vector store for semantic search (Optimisation #3)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.artcb.ir.models import IRGraph, IRNode

logger = logging.getLogger("artcb.memory.vector_store_faiss")

# Try to import FAISS (optional dependency)
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not available - falling back to basic search")


class VectorStoreFAISS:
    """FAISS-accelerated vector store for semantic search."""

    def __init__(self, embedding_dim: int = 384, use_gpu: bool = False) -> None:
        """Initialize FAISS vector store.

        Args:
            embedding_dim: Dimension of embeddings (default 384 for all-MiniLM-L6-v2)
            use_gpu: Whether to use GPU acceleration if available
        """
        self.embedding_dim = embedding_dim
        self.use_gpu = use_gpu and FAISS_AVAILABLE

        if not FAISS_AVAILABLE:
            raise ImportError(
                "FAISS not installed. Install with: pip install faiss-cpu or faiss-gpu"
            )

        # Create FAISS index (L2 distance)
        self.index = faiss.IndexFlatL2(embedding_dim)

        # Try GPU if requested
        if self.use_gpu and faiss.get_num_gpus() > 0:
            try:
                res = faiss.StandardGpuResources()
                self.index = faiss.index_cpu_to_gpu(res, 0, self.index)
                logger.info("FAISS GPU acceleration enabled")
            except Exception as e:
                logger.warning(f"GPU init failed, using CPU: {e}")
                self.use_gpu = False

        # Metadata storage
        self._node_metadata: list[tuple[str, IRNode]] = []
        self._graph_ids: set[str] = set()

    def _simple_embedding(self, text: str) -> np.ndarray:
        """Simple TF-IDF-like embedding (fallback without sentence-transformers).

        For production, use sentence-transformers:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
            return model.encode([text])[0]
        """
        # Character-level features (simple but fast)
        features = np.zeros(self.embedding_dim, dtype=np.float32)

        # Normalize text
        text_lower = text.lower()

        # Character frequency features (first 256 dims)
        for i, char in enumerate(text_lower[:256]):
            features[i] = ord(char) / 255.0

        # Length features
        features[256] = min(len(text) / 1000.0, 1.0)

        # Word count
        features[257] = min(len(text.split()) / 100.0, 1.0)

        # Normalize to unit vector
        norm = np.linalg.norm(features)
        if norm > 0:
            features = features / norm

        return features

    def index_graph(self, graph: IRGraph) -> None:
        """Index all nodes from a graph."""
        if graph.graph_id in self._graph_ids:
            logger.debug("Graph %s already indexed, skipping", graph.graph_id)
            return

        embeddings = []
        for node in graph.nodes:
            emb = self._simple_embedding(node.txt)
            embeddings.append(emb)
            self._node_metadata.append((graph.graph_id, node))

        if embeddings:
            embeddings_array = np.array(embeddings, dtype=np.float32)
            self.index.add(embeddings_array)
            self._graph_ids.add(graph.graph_id)
            logger.debug(
                "Indexed graph_id=%s nodes=%d total_nodes=%d",
                graph.graph_id,
                len(embeddings),
                self.index.ntotal,
            )

    def search(
        self,
        query: str,
        graph_id: str | None = None,
        top_k: int = 3,
    ) -> list[dict]:
        """Search for similar nodes using FAISS.

        Args:
            query: Search query text
            graph_id: Optional graph ID to filter results
            top_k: Number of results to return

        Returns:
            List of dicts with node info and similarity scores
        """
        if self.index.ntotal == 0:
            return []

        # Encode query
        query_emb = self._simple_embedding(query)
        query_array = np.array([query_emb], dtype=np.float32)

        # Search (returns L2 distances, lower is better)
        distances, indices = self.index.search(query_array, min(top_k * 2, self.index.ntotal))

        # Convert to results
        results = []
        for dist, idx in zip(distances[0], indices[0], strict=False):
            if idx < 0 or idx >= len(self._node_metadata):
                continue

            gid, node = self._node_metadata[idx]

            # Filter by graph_id if specified
            if graph_id and gid != graph_id:
                continue

            # Convert L2 distance to similarity score (0-1, higher is better)
            similarity = 1.0 / (1.0 + dist)

            results.append({
                "graph_id": gid,
                "node_id": node.id,
                "score": round(float(similarity), 4),
                "similarity": round(float(similarity), 4),  # Ajout clé similarity
                "text": node.txt,
                "type": node.t,
                "symbol": node.sym,
            })

            if len(results) >= top_k:
                break

        return results

    def clear(self) -> None:
        """Clear all indexed data."""
        self.index.reset()
        self._node_metadata.clear()
        self._graph_ids.clear()
        logger.debug("FAISS index cleared")

    @property
    def total_nodes(self) -> int:
        """Total number of indexed nodes."""
        return self.index.ntotal

    @property
    def is_gpu_enabled(self) -> bool:
        """Whether GPU acceleration is active."""
        return self.use_gpu

