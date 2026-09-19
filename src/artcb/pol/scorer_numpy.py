"""NumPy-vectorized PoL scorer for batch processing (Optimisation #9).

Seuil PoL : IMMUTABLE_POL_THRESHOLD (tokenomics.py) — jamais depuis .env.
Coherent avec scorer.py : le seuil est immuable dans les deux variantes du scorer.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from dataclasses import dataclass

import numpy as np

from src.artcb.config import load_settings
from src.artcb.ir.models import IRGraph
from src.artcb.tokenomics import IMMUTABLE_POL_THRESHOLD

logger = logging.getLogger("artcb.pol.scorer_numpy")


@dataclass(frozen=True)
class PolMetricsBatch:
    """Batch PoL metrics for multiple graphs."""
    delta_compression: np.ndarray
    validation_rate: np.ndarray
    retrieval_accuracy: np.ndarray
    pol_score: np.ndarray
    block_accepted: np.ndarray

    def to_list(self) -> list[dict]:
        """Convert to list of dicts."""
        return [
            {
                "delta_compression": float(self.delta_compression[i]),
                "validation_rate": float(self.validation_rate[i]),
                "retrieval_accuracy": float(self.retrieval_accuracy[i]),
                "pol_score": float(self.pol_score[i]),
                "block_accepted": bool(self.block_accepted[i]),
            }
            for i in range(len(self.pol_score))
        ]


class PolScorerNumPy:
    """Vectorized PoL scorer using NumPy for batch processing."""

    def __init__(
        self,
        alpha: float | None = None,
        beta: float | None = None,
        gamma: float | None = None,
        threshold: float | None = None,
    ) -> None:
        settings = load_settings()
        self.alpha = alpha if alpha is not None else settings.pol_alpha
        self.beta = beta if beta is not None else settings.pol_beta
        self.gamma = gamma if gamma is not None else settings.pol_gamma
        # IMMUTABLE : le seuil PoL est toujours 0.6 — jamais depuis .env.
        self.threshold = threshold if threshold is not None else IMMUTABLE_POL_THRESHOLD

    def score_batch(
        self,
        graphs: list[IRGraph],
        nodes_validated: list[int] | None = None,
        nodes_proposed: list[int] | None = None,
        nodes_retrieved: list[int] | None = None,
        nodes_correct: list[int] | None = None,
    ) -> PolMetricsBatch:
        """Score multiple graphs in parallel using NumPy vectorization.

        Args:
            graphs: List of IR graphs to score
            nodes_validated: List of validated node counts (optional)
            nodes_proposed: List of proposed node counts (optional)
            nodes_retrieved: List of retrieved node counts (optional)
            nodes_correct: List of correct node counts (optional)

        Returns:
            Batch PoL metrics
        """
        n = len(graphs)

        # Convert to numpy arrays
        if nodes_proposed is None:
            proposed = np.array([len(g.nodes) for g in graphs], dtype=np.float32)
        else:
            proposed = np.array(nodes_proposed, dtype=np.float32)

        validated = proposed.copy() if nodes_validated is None else np.array(nodes_validated, dtype=np.float32)

        # Ensure validated <= proposed
        proposed = np.maximum(proposed, 1.0)
        validated = np.minimum(validated, proposed)

        retrieved = proposed.copy() if nodes_retrieved is None else np.array(nodes_retrieved, dtype=np.float32)

        if nodes_correct is None:
            correct = np.array([
                retrieved[i] if graphs[i].verify_integrity() else 0.0
                for i in range(n)
            ], dtype=np.float32)
        else:
            correct = np.array(nodes_correct, dtype=np.float32)

        # Compute source lengths and IR sizes (vectorized)
        source_lens = np.array([max(len(g.source_text), 1) for g in graphs], dtype=np.float32)
        ir_sizes = np.array([len(g.to_json(indent=None)) for g in graphs], dtype=np.float32)

        # Compute delta compression (vectorized)
        delta_compression = np.clip(1.0 - (ir_sizes / source_lens), 0.0, 1.0)

        # Compute validation rate (vectorized)
        validation_rate = validated / proposed

        # Compute retrieval accuracy (vectorized)
        retrieval_accuracy = correct / np.maximum(retrieved, 1.0)

        # Compute PoL scores (vectorized)
        pol_scores = (
            self.alpha * delta_compression
            + self.beta * validation_rate
            + self.gamma * retrieval_accuracy
        )

        # Determine block acceptance (vectorized)
        block_accepted = pol_scores >= self.threshold

        logger.debug(
            "Scored %d graphs in batch: mean_pol=%.4f accepted=%d",
            n,
            np.mean(pol_scores),
            np.sum(block_accepted),
        )

        return PolMetricsBatch(
            delta_compression=np.round(delta_compression, 4),
            validation_rate=np.round(validation_rate, 4),
            retrieval_accuracy=np.round(retrieval_accuracy, 4),
            pol_score=np.round(pol_scores, 4),
            block_accepted=block_accepted,
        )

    @staticmethod
    def split_reward_batch(
        block_rewards: np.ndarray,
        contributor_scores: list[dict[str, float]],
    ) -> list[dict[str, float]]:
        """Split rewards for multiple blocks using vectorized operations.

        Args:
            block_rewards: Array of block rewards
            contributor_scores: List of dicts mapping addresses to scores

        Returns:
            List of dicts mapping addresses to reward amounts
        """
        results = []

        for reward, scores in zip(block_rewards, contributor_scores, strict=False):
            total = sum(scores.values())
            if total <= 0:
                results.append({k: 0.0 for k in scores})
            else:
                # Vectorize the split calculation
                addresses = list(scores.keys())
                score_array = np.array([scores[addr] for addr in addresses], dtype=np.float32)
                reward_array = (reward * score_array / total).round(8)
                results.append(dict(zip(addresses, reward_array, strict=False)))

        return results

