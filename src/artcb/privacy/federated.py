"""Agrégateur fédéré ARTCB — FedAvg sur vecteurs chiffrés homomorphiquement.

Architecture Federated Learning avec HE :

    Participant A → encrypt(vecteur_A) → pool ARTCB
    Participant B → encrypt(vecteur_B) → pool ARTCB
    Participant C → encrypt(vecteur_C) → pool ARTCB
                                            ↓
                              FederatedAggregator.aggregate()
                              (addition homomorphique — AUCUN déchiffrement)
                                            ↓
                              vecteur_agrégé_chiffré → bloc ARTCB
                              (le serveur ne voit jamais les données brutes)

Les participants peuvent ensuite déchiffrer le résultat agrégé avec leur clé.

Activation :
    ARTCB_HOMOMORPHIC_MODE=true  → confidentialité totale
    ARTCB_HOMOMORPHIC_MODE=false → mode classique sans chiffrement
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.artcb.privacy.homomorphic import HECipherVector, HomomorphicProcessor

logger = logging.getLogger("artcb.privacy.federated")

_HOMOMORPHIC_MODE = os.getenv("ARTCB_HOMOMORPHIC_MODE", "false").lower() == "true"


@dataclass
class FederatedContribution:
    """Contribution chiffrée d'un participant au round fédéré."""
    participant_id: str
    cipher_vector: HECipherVector
    pol_score: float
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FederatedRound:
    """Un round d'agrégation fédérée — contient les contributions et le résultat."""
    round_id: str
    contributions: list[FederatedContribution] = field(default_factory=list)
    aggregated_cipher: HECipherVector | None = None
    aggregated_pol_score: float = 0.0
    participant_count: int = 0
    timestamp_start: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    timestamp_end: str | None = None
    homomorphic: bool = _HOMOMORPHIC_MODE

    def summary(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "participant_count": self.participant_count,
            "aggregated_pol_score": round(self.aggregated_pol_score, 4),
            "homomorphic": self.homomorphic,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "has_aggregated_result": self.aggregated_cipher is not None,
        }


class FederatedAggregator:
    """Orchestrateur FedAvg côté serveur ARTCB.

    Le serveur ne déchiffre JAMAIS les contributions individuelles.
    Il agrège uniquement les ciphertexts (opération homomorphique).

    Usage :
        agg = FederatedAggregator()
        agg.add_contribution(participant_id, cipher_vector, pol_score)
        agg.add_contribution(...)
        round_result = agg.finalize()

        # round_result.aggregated_cipher est gravé dans ARTCB
        # Chaque participant peut déchiffrer avec sa propre clé
    """

    def __init__(self) -> None:
        self._contributions: list[FederatedContribution] = []

    def add_contribution(
        self,
        participant_id: str,
        cipher_vector: HECipherVector,
        pol_score: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Ajoute la contribution chiffrée d'un participant."""
        contrib = FederatedContribution(
            participant_id=participant_id,
            cipher_vector=cipher_vector,
            pol_score=pol_score,
            metadata=metadata or {},
        )
        self._contributions.append(contrib)
        logger.debug(
            "Contribution reçue — participant=%s pol=%.3f mode=%s",
            participant_id, pol_score, cipher_vector.mode
        )

    def finalize(self, round_id: str | None = None) -> FederatedRound:
        """Agrège toutes les contributions et retourne le round finalisé.

        Le serveur effectue l'addition homomorphique des ciphertexts.
        Aucun déchiffrement individuel n'est effectué.
        """
        import uuid as _uuid
        rid = round_id or _uuid.uuid4().hex[:12]

        if not self._contributions:
            raise ValueError("Aucune contribution à agréger — round vide")

        # Agrégation des vecteurs chiffrés (addition homomorphique)
        ciphers = [c.cipher_vector for c in self._contributions]
        aggregated = HomomorphicProcessor.aggregate(ciphers)

        # Score PoL moyen pondéré (FedAvg standard)
        total_pol = sum(c.pol_score for c in self._contributions)
        avg_pol = total_pol / len(self._contributions)

        round_result = FederatedRound(
            round_id=rid,
            contributions=list(self._contributions),
            aggregated_cipher=aggregated,
            aggregated_pol_score=avg_pol,
            participant_count=len(self._contributions),
            timestamp_end=datetime.now(UTC).isoformat(),
            homomorphic=_HOMOMORPHIC_MODE,
        )

        logger.info(
            "Round %s finalisé — %d participants, PoL moyen=%.3f, mode=%s",
            rid, len(self._contributions), avg_pol,
            "homomorphique" if _HOMOMORPHIC_MODE else "classique"
        )

        # Reset pour le prochain round
        self._contributions = []
        return round_result

    def contribution_count(self) -> int:
        return len(self._contributions)

    def reset(self) -> None:
        self._contributions = []
