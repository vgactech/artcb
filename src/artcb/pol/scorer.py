"""Proof-of-Learning scorer — CDC §3.2.4.

Seuil PoL : IMMUTABLE_POL_THRESHOLD (tokenomics.py) — jamais depuis .env.
Coefficients alpha, beta, gamma : configurables via .env pour le dev uniquement.
En production, seul le fondateur peut les modifier via vote de gouvernance.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.artcb.config import load_settings
from src.artcb.ir.models import IRGraph
from src.artcb.tokenomics import IMMUTABLE_POL_THRESHOLD


@dataclass(frozen=True)
class PolMetrics:
    delta_compression: float
    validation_rate: float
    retrieval_accuracy: float
    pol_score: float
    block_accepted: bool

    def to_dict(self) -> dict:
        return {
            "delta_compression": self.delta_compression,
            "validation_rate": self.validation_rate,
            "retrieval_accuracy": self.retrieval_accuracy,
            "pol_score": round(self.pol_score, 4),
            "block_accepted": self.block_accepted,
        }


class PolScorer:
    """PoL_score = α×Δcompression + β×validation_rate + γ×retrieval_accuracy."""

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
        # Le parametre threshold (si fourni explicitement en test) est accepte
        # pour les tests unitaires uniquement — pas en production.
        self.threshold = threshold if threshold is not None else IMMUTABLE_POL_THRESHOLD

    def score(
        self,
        graph: IRGraph,
        *,
        nodes_validated: int | None = None,
        nodes_proposed: int | None = None,
        nodes_retrieved: int | None = None,
        nodes_correct: int | None = None,
        ir_size: int | None = None,
    ) -> PolMetrics:
        proposed = nodes_proposed if nodes_proposed is not None else len(graph.nodes)
        validated = nodes_validated if nodes_validated is not None else proposed
        proposed = max(proposed, 1)
        validated = min(validated, proposed)

        if nodes_retrieved is None:
            nodes_retrieved = proposed
        if nodes_correct is None:
            nodes_correct = nodes_retrieved if graph.verify_integrity() else 0

        source_len = max(len(graph.source_text), 1)
        if ir_size is None:
            ir_size = len(graph.to_json(indent=None))
        delta_compression = max(0.0, min(1.0, 1.0 - (ir_size / source_len)))

        validation_rate = validated / proposed
        retrieval_accuracy = nodes_correct / max(nodes_retrieved, 1)

        pol_score = (
            self.alpha * delta_compression
            + self.beta * validation_rate
            + self.gamma * retrieval_accuracy
        )

        return PolMetrics(
            delta_compression=round(delta_compression, 4),
            validation_rate=round(validation_rate, 4),
            retrieval_accuracy=round(retrieval_accuracy, 4),
            pol_score=round(pol_score, 4),
            block_accepted=pol_score >= self.threshold,
        )

    @staticmethod
    def split_reward(block_reward: float, contributor_scores: dict[str, float]) -> dict[str, float]:
        """Collective split — TOKENOMICS §6.2, conserved to the satoshi."""
        from src.artcb.economics.satoshi import (
            allocate_satoshi,
            artcb_to_satoshi,
            satoshi_to_artcb,
        )

        allocated = allocate_satoshi(contributor_scores, artcb_to_satoshi(block_reward))
        return {address: satoshi_to_artcb(satoshi) for address, satoshi in allocated.items()}
