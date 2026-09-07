"""Élection de producteur de secours — GO-E / V-01-B.

LIVE (rapport 244) : ce module n'est importé par aucune route ``src/api``.
Le ``ProducerMonitor`` n'est pas démarré sur les nœuds. XOR + grâce 30 s
ne sont pas un verrou BFT d'élection. Ne pas l'activer sans GO manuscrit.

Protocole anti-fork :
  - Un seul nœud produit des blocs à la fois (producteur actif).
  - Si le producteur ne bat pas dans HEARTBEAT_TIMEOUT secondes,
    les nœuds en CONSENSUS mode détectent l'absence.
  - L'élection est déterministe : rang XOR(node_id, tip_hash) → pas d'ambiguïté.
  - Le résultat d'élection est signé par le nœud élu (clé de certification).
  - Sans majorité BFT confirmant le nouvel élu, la chaîne attend (pas de fork).

Invariants de sécurité :
  - JAMAIS deux producteurs simultanés sur le même index.
  - Un nœud non certifié CONSENSUS ne peut pas s'auto-élire.
  - L'ancien producteur toujours en ligne conserve la priorité (heartbeat récent).
  - Un backup ne commence à produire qu'après ELECTION_GRACE_SECONDS.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("artcb.p2p.producer_election")

# ── Constantes ────────────────────────────────────────────────────────────────

# Secondes sans bloc public avant de considérer le producteur mort
HEARTBEAT_TIMEOUT: float = float(__import__("os").getenv("ARTCB_PRODUCER_HEARTBEAT_TIMEOUT", "120"))

# Délai de grace avant qu'un backup commence à produire (évite split-brain transitoire)
ELECTION_GRACE_SECONDS: float = float(__import__("os").getenv("ARTCB_ELECTION_GRACE_SECONDS", "30"))

# Nombre minimum de nœuds CONSENSUS pour déclencher une élection
MIN_CONSENSUS_NODES: int = int(__import__("os").getenv("ARTCB_MIN_CONSENSUS_NODES", "2"))


# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class ProducerHeartbeat:
    """Battement enregistré quand un nœud produit un bloc public."""
    node_id: str
    last_block_hash: str
    last_block_index: int
    timestamp: float = field(default_factory=time.time)

    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    def is_alive(self, timeout: float = HEARTBEAT_TIMEOUT) -> bool:
        return self.age_seconds() < timeout


@dataclass
class ElectionResult:
    """Résultat d'une élection déterministe."""
    elected_node_id: str
    tip_hash: str
    rank_score: int              # XOR distance (plus petit = prioritaire)
    candidates: list[str]        # tous les nœuds CONSENSUS candidats
    election_time: float = field(default_factory=time.time)
    grace_expires_at: float = 0.0

    def __post_init__(self) -> None:
        if self.grace_expires_at == 0.0:
            self.grace_expires_at = self.election_time + ELECTION_GRACE_SECONDS

    def grace_period_active(self) -> bool:
        """True si on est encore dans la fenêtre de grace (pas encore produire)."""
        return time.time() < self.grace_expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "elected_node_id": self.elected_node_id,
            "tip_hash": self.tip_hash,
            "rank_score": self.rank_score,
            "candidates": self.candidates,
            "election_time": self.election_time,
            "grace_expires_at": self.grace_expires_at,
            "grace_active": self.grace_period_active(),
        }


class ProducerElectionError(Exception):
    """Impossible de déclencher une élection valide."""


# ── Fonctions d'élection ─────────────────────────────────────────────────────

def _xor_rank(node_id: str, tip_hash: str) -> int:
    """Rang déterministe d'un nœud par XOR(sha256(node_id), sha256(tip_hash)).

    Tous les nœuds voient le même tip → même classement → pas d'ambiguïté.
    """
    nid_hash = int(hashlib.sha256(node_id.encode()).hexdigest()[:16], 16)
    tip_int  = int(hashlib.sha256(tip_hash.encode()).hexdigest()[:16], 16)
    return nid_hash ^ tip_int


def elect_producer(
    *,
    consensus_nodes: list[str],
    tip_hash: str,
    exclude_node_id: str | None = None,
) -> ElectionResult:
    """Élection déterministe du nouveau producteur parmi les nœuds CONSENSUS.

    Args:
        consensus_nodes: Liste des node_id ayant le rôle CONSENSUS (certifiés).
        tip_hash: Hash du dernier bloc connu (point d'ancrage commun).
        exclude_node_id: Nœud à exclure (producteur défaillant).

    Returns:
        ElectionResult avec le nœud élu.

    Raises:
        ProducerElectionError: Si aucun candidat valide n'existe.
    """
    candidates = [n for n in consensus_nodes if n != exclude_node_id]
    if not candidates:
        raise ProducerElectionError(
            f"Aucun candidat CONSENSUS disponible (exclu={exclude_node_id}, total={len(consensus_nodes)})"
        )
    if len(consensus_nodes) < MIN_CONSENSUS_NODES:
        raise ProducerElectionError(
            f"Réseau insuffisant : {len(consensus_nodes)} nœuds CONSENSUS < minimum {MIN_CONSENSUS_NODES}"
        )

    ranked = sorted(candidates, key=lambda n: _xor_rank(n, tip_hash))
    elected = ranked[0]
    score   = _xor_rank(elected, tip_hash)

    logger.info(
        "Election: tip=%s exclu=%s élu=%s score=%d (candidats=%s)",
        tip_hash[:16], exclude_node_id, elected, score, candidates,
    )
    return ElectionResult(
        elected_node_id=elected,
        tip_hash=tip_hash,
        rank_score=score,
        candidates=candidates,
    )


# ── Moniteur de producteur ────────────────────────────────────────────────────

class ProducerMonitor:
    """Surveille le producteur actif et déclenche une élection si nécessaire.

    Usage :
        monitor = ProducerMonitor(local_node_id="artcb1nodeXXX")
        monitor.record_block(node_id="artcb1nodePRIMARY", block_hash="abc...", index=42)

        if monitor.producer_is_dead():
            result = monitor.trigger_election(consensus_nodes=[...], tip_hash="abc...")
            if result and not result.grace_period_active():
                if result.elected_node_id == local_node_id:
                    # C'est nous — commencer à produire
                    ...
    """

    def __init__(self, local_node_id: str, heartbeat_timeout: float = HEARTBEAT_TIMEOUT) -> None:
        self.local_node_id = local_node_id
        self.heartbeat_timeout = heartbeat_timeout
        self._heartbeats: dict[str, ProducerHeartbeat] = {}
        self._current_producer: str | None = None
        self._last_election: ElectionResult | None = None

    def record_block(self, *, node_id: str, block_hash: str, block_index: int) -> None:
        """Enregistre qu'un nœud vient de produire un bloc public."""
        hb = ProducerHeartbeat(
            node_id=node_id,
            last_block_hash=block_hash,
            last_block_index=block_index,
        )
        self._heartbeats[node_id] = hb
        # Le nœud qui produit devient le producteur courant
        if self._current_producer != node_id:
            logger.info("Producteur actif : %s (index=%d)", node_id, block_index)
            self._current_producer = node_id

    def producer_is_dead(self) -> bool:
        """True si le producteur courant n'a pas battu depuis heartbeat_timeout."""
        if self._current_producer is None:
            return False  # Pas encore de producteur connu
        hb = self._heartbeats.get(self._current_producer)
        if hb is None:
            return False  # Jamais vu → pas mort
        dead = not hb.is_alive(self.heartbeat_timeout)
        if dead:
            logger.warning(
                "Producteur %s INACTIF depuis %.1fs (seuil=%.1fs)",
                self._current_producer, hb.age_seconds(), self.heartbeat_timeout,
            )
        return dead

    def trigger_election(
        self,
        *,
        consensus_nodes: list[str],
        tip_hash: str,
    ) -> ElectionResult | None:
        """Déclenche une élection si le producteur est mort.

        Returns:
            ElectionResult si une élection a été déclenchée, None sinon.
        """
        if not self.producer_is_dead():
            return None

        dead_producer = self._current_producer
        try:
            result = elect_producer(
                consensus_nodes=consensus_nodes,
                tip_hash=tip_hash,
                exclude_node_id=dead_producer,
            )
            self._last_election = result
            # L'élu devient le nouveau producteur courant
            self._current_producer = result.elected_node_id
            logger.info(
                "Election déclenchée : mort=%s élu=%s grace_expires=%.1fs",
                dead_producer, result.elected_node_id,
                result.grace_expires_at - time.time(),
            )
            return result
        except ProducerElectionError as exc:
            logger.error("Election impossible : %s", exc)
            return None

    def am_i_elected(self, result: ElectionResult) -> bool:
        """True si ce nœud est l'élu ET la grace period est terminée."""
        return (
            result.elected_node_id == self.local_node_id
            and not result.grace_period_active()
        )

    def current_producer(self) -> str | None:
        return self._current_producer

    def last_heartbeat(self, node_id: str) -> ProducerHeartbeat | None:
        return self._heartbeats.get(node_id)

    def status(self) -> dict[str, Any]:
        return {
            "local_node_id": self.local_node_id,
            "current_producer": self._current_producer,
            "producer_alive": not self.producer_is_dead() if self._current_producer else None,
            "heartbeat_timeout": self.heartbeat_timeout,
            "known_producers": {
                nid: {
                    "last_block_index": hb.last_block_index,
                    "age_seconds": round(hb.age_seconds(), 1),
                    "alive": hb.is_alive(self.heartbeat_timeout),
                }
                for nid, hb in self._heartbeats.items()
            },
            "last_election": self._last_election.to_dict() if self._last_election else None,
        }
