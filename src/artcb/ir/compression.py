"""Graph compression utilities (Optimisation #6)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import gzip
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.artcb.ir.models import IRGraph

logger = logging.getLogger("artcb.ir.compression")


class GraphCompressor:
    """Compress IR graphs for efficient storage."""

    @staticmethod
    def compress_graph(graph: IRGraph, level: int = 6) -> bytes:
        """Compress graph to gzipped JSON bytes.

        Args:
            graph: IR graph to compress
            level: Compression level (1-9, default 6)

        Returns:
            Compressed bytes
        """
        # Serialize to JSON
        json_str = graph.to_json(indent=None)
        json_bytes = json_str.encode('utf-8')

        # Compress with gzip
        compressed = gzip.compress(json_bytes, compresslevel=level)

        compression_ratio = 1.0 - (len(compressed) / len(json_bytes))
        logger.debug(
            "Compressed graph_id=%s original=%d compressed=%d ratio=%.2f%%",
            graph.graph_id,
            len(json_bytes),
            len(compressed),
            compression_ratio * 100,
        )

        return compressed

    @staticmethod
    def decompress_graph(compressed: bytes) -> IRGraph:
        """Decompress graph from gzipped JSON bytes.

        Args:
            compressed: Compressed bytes

        Returns:
            Decompressed IR graph
        """
        from src.artcb.ir.models import IRGraph

        # Decompress
        json_bytes = gzip.decompress(compressed)
        json_str = json_bytes.decode('utf-8')

        # Deserialize
        data = json.loads(json_str)
        graph = IRGraph.from_dict(data)

        logger.debug(
            "Decompressed graph_id=%s compressed=%d original=%d",
            graph.graph_id,
            len(compressed),
            len(json_bytes),
        )

        return graph

    @staticmethod
    def estimate_compression_ratio(graph: IRGraph) -> float:
        """Estimate compression ratio without actually compressing.

        Args:
            graph: IR graph

        Returns:
            Estimated compression ratio (0-1, higher is better)
        """
        json_str = graph.to_json(indent=None)
        len(json_str.encode('utf-8'))

        # Estimate based on repetition and structure
        # Real compression would be better, but this is fast
        unique_chars = len(set(json_str))
        total_chars = len(json_str)

        # Simple heuristic: more repetition = better compression
        repetition_factor = 1.0 - (unique_chars / total_chars)
        estimated_ratio = repetition_factor * 0.7  # Typical gzip achieves ~70% of theoretical max

        return round(estimated_ratio, 4)

