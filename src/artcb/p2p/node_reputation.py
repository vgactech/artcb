"""Réputation des nœuds P2P — GO-M.

Rapport 238 §32 — architecture complète :
  "PoL + KCG + Evidence + Validation + Utility + Reward"
  
Le réseau doit pouvoir choisir ses producteurs sur la qualité prouvée,
pas seulement sur une élection XOR aveugle (GO-E).

Architecture GO-M :
  NodeReputationRecord — métriques par nœud, stockage binaire struct pack
  ReputationLedger     — index binaire persistant (pas JSONL)
  ReputationEngine     — score agrégé 0.0–1.0 + intégration ProducerMonitor

Intégration GO-E :
  elect_producer_by_reputation() remplace l'élection XOR pure par :
  rank = XOR_distance × (2 - reputation_score)
  → nœud fiable (score=1.0) obtient un avantage ×1.0 sur le rang
  → nœud peu fiable (score=0.0) obtient un malus ×2.0

Format binaire :
  node_id(40 bytes) + uptime_pct(4) + blocks_produced(4) + bft_votes_ok(4)
  + bft_votes_total(4) + fraud_detections(4) + latency_ms_avg(4)
  + last_seen(8) + reserved(8) = 80 bytes par enregistrement

Stockage :
  data/p2p/reputation/
    index.bin     — NodeReputationRecord × N (80 bytes chacun)
    manifest.bin  — ARMN + version + count + last_updated

Le JSON est uniquement exposé via l'API humaine (GET /p2p/reputation).
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.p2p.node_reputation")

# ── Constantes ────────────────────────────────────────────────────────────────

REPUTATION_VERSION: int = 1
MANIFEST_MAGIC = b"ARMN"   # ARTCB Reputation Manifest Node
RECORD_SIZE = 80            # bytes par NodeReputationRecord
MANIFEST_SIZE = 24          # magic(4)+version(2)+count(4)+last_updated(8)+reserved(6)

# Seuil de promotion suggérée : score > AUTO_PROMOTE_THRESHOLD depuis MIN_DAYS_PROMOTE jours
AUTO_PROMOTE_THRESHOLD: float = float(
    __import__("os").getenv("ARTCB_REPUTATION_PROMOTE_THRESHOLD", "0.85")
)
MIN_OBSERVATIONS_PROMOTE: int = int(
    __import__("os").getenv("ARTCB_REPUTATION_MIN_OBS", "10")
)


class ReputationError(Exception):
    """Erreur du système de réputation."""


# ── NodeReputationRecord ──────────────────────────────────────────────────────

@dataclass
class NodeReputationRecord:
    """Métriques de réputation d'un nœud P2P.

    Toutes les valeurs sont mesurées, pas inventées (rapport 238 §19 : honnêteté).
    """
    node_id: str
    uptime_pct: float = 0.0          # % de temps en ligne (0.0–100.0)
    blocks_produced: int = 0          # blocs publics produits avec succès
    bft_votes_ok: int = 0             # votes BFT cohérents avec le consensus
    bft_votes_total: int = 0          # total votes BFT émis
    fraud_detections: int = 0         # fois où ce nœud a été détecté frauduleux
    latency_ms_avg: float = 0.0       # latence moyenne mesurée (ms)
    last_seen: float = field(default_factory=time.time)

    @property
    def bft_accuracy(self) -> float:
        """Précision BFT : ratio votes cohérents / total."""
        if self.bft_votes_total == 0:
            return 1.0  # pas encore vu = bénéfice du doute
        return self.bft_votes_ok / self.bft_votes_total

    @property
    def total_observations(self) -> int:
        return self.blocks_produced + self.bft_votes_total

    def score(self) -> float:
        """Score de réputation agrégé 0.0–1.0.

        Formule :
          uptime       : 25 % du score
          bft_accuracy : 35 % du score
          no_fraud     : 30 % du score (décroît avec les détections de fraude)
          latency      : 10 % du score (meilleur si < 1000ms)

        Pénalité directe : chaque fraude soustrait 0.15 du score final.
        → 4 fraudes : −0.60 sur le score brut → garantit score < 0.60
          même avec uptime=100% et bft=100%.

        Rapport 238 §19 : "Mesurer, pas inventer."
        """
        uptime_score  = min(self.uptime_pct / 100.0, 1.0)
        bft_score     = self.bft_accuracy
        # Chaque détection de fraude annule la composante fraude (0.50/fraude → 0 dès 2)
        fraud_score   = max(0.0, 1.0 - self.fraud_detections * 0.50)
        latency_score = max(0.0, 1.0 - self.latency_ms_avg / 1000.0) if self.latency_ms_avg > 0 else 1.0

        raw = (
            0.25 * uptime_score
            + 0.35 * bft_score
            + 0.30 * fraud_score
            + 0.10 * latency_score
        )
        # Pénalité directe par fraude : −0.15 par détection (cumul, plafonné à 0)
        penalty = self.fraud_detections * 0.15
        return round(min(max(raw - penalty, 0.0), 1.0), 4)

    def promote_suggestion(self) -> bool:
        """True si le nœud remplit les critères de promotion CONSENSUS automatique."""
        return (
            self.score() >= AUTO_PROMOTE_THRESHOLD
            and self.total_observations >= MIN_OBSERVATIONS_PROMOTE
            and self.fraud_detections == 0
        )

    def to_binary(self) -> bytes:
        """Sérialise en binaire compact struct pack (80 bytes fixes)."""
        nid   = self.node_id.encode("ascii").ljust(40, b"\x00")[:40]
        up    = struct.pack(">f", float(self.uptime_pct))
        bp    = struct.pack(">I", int(self.blocks_produced))
        bvok  = struct.pack(">I", int(self.bft_votes_ok))
        bvtot = struct.pack(">I", int(self.bft_votes_total))
        fraud = struct.pack(">I", int(self.fraud_detections))
        lat   = struct.pack(">f", float(self.latency_ms_avg))
        ls    = struct.pack(">d", float(self.last_seen))
        rsv   = b"\x00" * 8   # reserved
        result = nid + up + bp + bvok + bvtot + fraud + lat + ls + rsv
        assert len(result) == RECORD_SIZE, f"BUG: {len(result)} != {RECORD_SIZE}"
        return result

    @classmethod
    def from_binary(cls, data: bytes) -> NodeReputationRecord:
        if len(data) < RECORD_SIZE:
            raise ReputationError(f"Record trop court : {len(data)} bytes (min {RECORD_SIZE})")
        node_id        = data[0:40].rstrip(b"\x00").decode("ascii")
        uptime_pct     = struct.unpack(">f", data[40:44])[0]
        blocks_produced = struct.unpack(">I", data[44:48])[0]
        bft_votes_ok   = struct.unpack(">I", data[48:52])[0]
        bft_votes_total = struct.unpack(">I", data[52:56])[0]
        fraud_detections = struct.unpack(">I", data[56:60])[0]
        latency_ms_avg = struct.unpack(">f", data[60:64])[0]
        last_seen      = struct.unpack(">d", data[64:72])[0]
        return cls(
            node_id=node_id,
            uptime_pct=float(uptime_pct),
            blocks_produced=int(blocks_produced),
            bft_votes_ok=int(bft_votes_ok),
            bft_votes_total=int(bft_votes_total),
            fraud_detections=int(fraud_detections),
            latency_ms_avg=float(latency_ms_avg),
            last_seen=float(last_seen),
        )

    def to_dict(self) -> dict[str, Any]:
        """Vue lisible pour l'API humaine uniquement."""
        return {
            "node_id": self.node_id,
            "score": self.score(),
            "uptime_pct": round(self.uptime_pct, 2),
            "blocks_produced": self.blocks_produced,
            "bft_accuracy": round(self.bft_accuracy, 4),
            "bft_votes_ok": self.bft_votes_ok,
            "bft_votes_total": self.bft_votes_total,
            "fraud_detections": self.fraud_detections,
            "latency_ms_avg": round(self.latency_ms_avg, 1),
            "last_seen": self.last_seen,
            "promote_suggestion": self.promote_suggestion(),
            "total_observations": self.total_observations,
        }


# ── ReputationLedger ──────────────────────────────────────────────────────────

class ReputationLedger:
    """Index binaire persistant des scores de réputation des nœuds.

    Stockage : data/p2p/reputation/index.bin (struct pack)
    Pas de JSONL. Pas de texte. Pas de JSON interne.
    """

    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / "p2p" / "reputation"
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path = self._root / "index.bin"
        self._manifest_path = self._root / "manifest.bin"
        self._records: dict[str, NodeReputationRecord] = {}
        self._load()

    def _write_manifest(self) -> None:
        data = (
            MANIFEST_MAGIC
            + struct.pack(">H", REPUTATION_VERSION)
            + struct.pack(">I", len(self._records))
            + struct.pack(">d", time.time())
            + b"\x00" * 6
        )
        self._manifest_path.write_bytes(data)

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        data = self._index_path.read_bytes()
        n = len(data) // RECORD_SIZE
        for i in range(n):
            chunk = data[i * RECORD_SIZE: (i + 1) * RECORD_SIZE]
            try:
                rec = NodeReputationRecord.from_binary(chunk)
                self._records[rec.node_id] = rec
            except Exception as exc:
                logger.warning("Reputation record %d corrompu : %s", i, exc)
        logger.debug("ReputationLedger chargé : %d nœuds", len(self._records))

    def _save(self) -> None:
        records = sorted(self._records.values(), key=lambda r: r.node_id)
        data = b"".join(r.to_binary() for r in records)
        self._index_path.write_bytes(data)
        self._write_manifest()
        logger.debug("ReputationLedger sauvegardé : %d nœuds", len(records))

    def get_or_create(self, node_id: str) -> NodeReputationRecord:
        if node_id not in self._records:
            self._records[node_id] = NodeReputationRecord(node_id=node_id)
        return self._records[node_id]

    def record_block_produced(self, node_id: str) -> None:
        rec = self.get_or_create(node_id)
        rec.blocks_produced += 1
        rec.last_seen = time.time()
        self._save()

    def record_bft_vote(self, node_id: str, *, correct: bool) -> None:
        rec = self.get_or_create(node_id)
        rec.bft_votes_total += 1
        if correct:
            rec.bft_votes_ok += 1
        rec.last_seen = time.time()
        self._save()

    def record_fraud(self, node_id: str) -> None:
        rec = self.get_or_create(node_id)
        rec.fraud_detections += 1
        logger.warning("Fraude enregistrée pour %s (total=%d)", node_id, rec.fraud_detections)
        self._save()

    def update_uptime(self, node_id: str, uptime_pct: float) -> None:
        rec = self.get_or_create(node_id)
        rec.uptime_pct = max(0.0, min(100.0, uptime_pct))
        self._save()

    def update_latency(self, node_id: str, latency_ms: float) -> None:
        rec = self.get_or_create(node_id)
        # Moyenne glissante (EWMA α=0.3)
        alpha = 0.3
        if rec.latency_ms_avg == 0.0:
            rec.latency_ms_avg = latency_ms
        else:
            rec.latency_ms_avg = alpha * latency_ms + (1 - alpha) * rec.latency_ms_avg
        self._save()

    def score(self, node_id: str) -> float:
        rec = self._records.get(node_id)
        return rec.score() if rec else 0.5  # nœud inconnu = score neutre

    def get(self, node_id: str) -> NodeReputationRecord | None:
        return self._records.get(node_id)

    def all_records(self) -> list[NodeReputationRecord]:
        return sorted(self._records.values(), key=lambda r: r.score(), reverse=True)

    def promote_candidates(self) -> list[str]:
        """Nœuds qui remplissent les critères de promotion CONSENSUS."""
        return [r.node_id for r in self._records.values() if r.promote_suggestion()]

    def node_count(self) -> int:
        return len(self._records)

    def stats(self) -> dict[str, Any]:
        """Vue humaine uniquement."""
        return {
            "node_count": self.node_count(),
            "promote_candidates": self.promote_candidates(),
            "top_nodes": [r.to_dict() for r in self.all_records()[:10]],
            "ledger_path": str(self._root),
        }


# ── ReputationEngine — intégration GO-E ──────────────────────────────────────

class ReputationEngine:
    """Intègre la réputation dans l'élection de producteur (GO-E).

    Rapport 238 §32 : PoL + Evidence + Validation → Reward
    Ici : Reputation + XOR → Election de producteur fiable.
    """

    def __init__(self, ledger: ReputationLedger) -> None:
        self.ledger = ledger

    def reputation_weighted_rank(self, node_id: str, tip_hash: str) -> float:
        """Rang d'élection pondéré par la réputation.

        rank = XOR_distance × (2 - reputation_score)
          → score=1.0 → facteur ×1.0 (avantage)
          → score=0.0 → facteur ×2.0 (désavantage)
          → score=0.5 → facteur ×1.5 (neutre)

        Nœud frauduleux (fraud_detections > 0) → rang = +∞ (jamais élu).

        Args:
            node_id: ID du nœud candidat.
            tip_hash: Hash du dernier bloc (point d'ancrage commun).

        Returns:
            Score de rang — plus petit = plus prioritaire.
        """
        import hashlib as _hl
        rec = self.ledger.get(node_id)
        # Disqualification immédiate pour tout nœud frauduleux
        if rec is not None and rec.fraud_detections > 0:
            return float("inf")
        xor = int(_hl.sha256(node_id.encode()).hexdigest()[:16], 16) ^ \
              int(_hl.sha256(tip_hash.encode()).hexdigest()[:16], 16)
        rep = self.ledger.score(node_id)
        return xor * (2.0 - rep)

    def elect_best_producer(
        self,
        *,
        consensus_nodes: list[str],
        tip_hash: str,
        exclude_node_id: str | None = None,
    ) -> str | None:
        """Élit le meilleur producteur en tenant compte de la réputation.

        Args:
            consensus_nodes: Nœuds CONSENSUS certifiés.
            tip_hash: Hash du tip actuel.
            exclude_node_id: Nœud exclu (défaillant).

        Returns:
            node_id du nœud élu, ou None si aucun candidat.
        """
        candidates = [n for n in consensus_nodes if n != exclude_node_id]
        if not candidates:
            return None
        elected = min(candidates, key=lambda n: self.reputation_weighted_rank(n, tip_hash))
        logger.info(
            "Election reputation : tip=%s exclu=%s élu=%s score=%.3f",
            tip_hash[:12], exclude_node_id, elected, self.ledger.score(elected),
        )
        return elected

    def top_k_producers(self, consensus_nodes: list[str], tip_hash: str, k: int = 3) -> list[str]:
        """Retourne les k meilleurs candidats producteurs triés par rang pondéré."""
        candidates = sorted(
            consensus_nodes,
            key=lambda n: self.reputation_weighted_rank(n, tip_hash),
        )
        return candidates[:k]
