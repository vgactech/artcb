"""KnowledgeWork — Chaîne KnowledgeID → WorkID → PoL → on-chain (R436).

Ce module implémente le dernier maillon de la chaîne ARTCB :

    KnowledgeRecord (src/artcb/knowledge/knowledge.py)
          ↓ knowledge_id
    UsageRecord (src/artcb/knowledge/usage.py)
          ↓ usage_id + pol_eligible
    PolMetrics (src/artcb/pol/scorer.py)
          ↓ pol_score + block_accepted + knowledge_id + usage_id
    KnowledgeWorkRecord  ← ce module (R436)
          ↓ work_id + pol_score + block_hash
    Blockchain on-chain (src/artcb/chain/manager.py)

Un KnowledgeWorkRecord est un artefact IMMUABLE (frozen=True) qui attache :
  - un KnowledgeID ARTCD à un WorkID (registre economics.workid)
  - les métriques PoL (pol_score, block_accepted) du calcul ARTCD
  - le hash de bloc on-chain (prouve l'inscription réelle — None si non encore inscrit)

Invariants :
  - Un KnowledgeWorkRecord ne peut PAS être modifié après création.
  - work_record_id = "KW" + sha256(knowledge_id + work_id + pol_score_str + created_at)[:24]
  - pol_score doit être >= 0.0 et <= 1.0
  - block_hash peut être None si le bloc n'a pas encore été inscrit (PENDING)
  - CERTIFIED_100=false — la chaîne complète n'est pas encore certifiée

Utilisation :
    from src.artcb.chain.knowledge_work import create_knowledge_work_record, KnowledgeWorkStore

    rec = create_knowledge_work_record(
        knowledge_id="K_abc",
        work_id="work_xyz",
        pol_score=0.72,
        block_accepted=True,
        usage_id="U_def",
        producer_id="agent_A",
    )
    store = KnowledgeWorkStore(data_dir=Path("data/knowledge_work"))
    store.save(rec)

    # Après inscription on-chain :
    sealed = store.seal_with_block_hash(rec.work_record_id, block_hash="0x1a2b3c…")

PROTOCOLE ARTCB — mode DEBUG actif.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.1'  # R436 — KnowledgeID → WorkID → PoL → on-chain

import contextlib
import fcntl
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.chain.knowledge_work")


# ── Dataclass principale ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class KnowledgeWorkRecord:
    """Artefact immuable reliant un KnowledgeID à un WorkID et au bloc on-chain (R436).

    Champs :
      work_record_id    : identifiant stable "KW" + sha256[:24]
      knowledge_id      : KnowledgeID ARTCD (KnowledgeRecord.knowledge_id)
      work_id           : WorkID économique (WorkRecord.work_id)
      pol_score         : score PoL [0.0, 1.0]
      block_accepted    : True si pol_score >= IMMUTABLE_POL_THRESHOLD
      created_at        : timestamp ISO UTC de création de ce record
      status            : "PENDING" (pas encore on-chain) | "SEALED" (bloc inscrit)
      block_hash        : hash du bloc on-chain (None si PENDING)
      usage_id          : UsageID ARTCD optionnel (maillon UsageRecord)
      producer_id       : identifiant de l'agent/wallet producteur
      metadata          : champs libres (job_id, session_id, node_id, …)
    """
    work_record_id:  str
    knowledge_id:    str
    work_id:         str
    pol_score:       float
    block_accepted:  bool
    created_at:      str
    status:          str                    # "PENDING" | "SEALED"
    block_hash:      str | None = None      # None tant que non inscrit on-chain
    usage_id:        str | None = None
    producer_id:     str = ""
    metadata:        dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_record_id": self.work_record_id,
            "knowledge_id":   self.knowledge_id,
            "work_id":        self.work_id,
            "pol_score":      round(self.pol_score, 6),
            "block_accepted": self.block_accepted,
            "created_at":     self.created_at,
            "status":         self.status,
            "block_hash":     self.block_hash,
            "usage_id":       self.usage_id,
            "producer_id":    self.producer_id,
            "metadata":       dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "KnowledgeWorkRecord":
        return cls(
            work_record_id=d["work_record_id"],
            knowledge_id=d["knowledge_id"],
            work_id=d["work_id"],
            pol_score=float(d["pol_score"]),
            block_accepted=bool(d["block_accepted"]),
            created_at=d["created_at"],
            status=d["status"],
            block_hash=d.get("block_hash"),
            usage_id=d.get("usage_id"),
            producer_id=d.get("producer_id", ""),
            metadata=dict(d.get("metadata", {})),
        )

    def is_sealed(self) -> bool:
        """True si le bloc on-chain a été inscrit (block_hash présent)."""
        return self.status == "SEALED" and self.block_hash is not None

    def seal(self, block_hash: str) -> "KnowledgeWorkRecord":
        """Retourne une copie SEALED avec le block_hash on-chain (frozen → nouvelle instance).

        Args:
            block_hash: hash du bloc on-chain (hex ou format natif blockchain).

        Returns:
            KnowledgeWorkRecord avec status="SEALED" et block_hash renseigné.
        """
        if not block_hash:
            raise ValueError("block_hash ne peut pas être vide pour sceller un KnowledgeWorkRecord")
        return KnowledgeWorkRecord(
            work_record_id=self.work_record_id,
            knowledge_id=self.knowledge_id,
            work_id=self.work_id,
            pol_score=self.pol_score,
            block_accepted=self.block_accepted,
            created_at=self.created_at,
            status="SEALED",
            block_hash=block_hash,
            usage_id=self.usage_id,
            producer_id=self.producer_id,
            metadata=self.metadata,
        )


# ── Fonction de construction ──────────────────────────────────────────────────

def _compute_work_record_id(
    *,
    knowledge_id: str,
    work_id: str,
    pol_score: float,
    created_at: str,
) -> str:
    """Calcule un work_record_id déterministe.

    Deux agents créant le même (knowledge_id, work_id, pol_score, created_at)
    obtiennent le même work_record_id — permet la déduplication inter-agents.
    """
    payload = json.dumps(
        {
            "knowledge_id": knowledge_id,
            "work_id": work_id,
            "pol_score": round(pol_score, 6),
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"KW{digest[:24]}"


def create_knowledge_work_record(
    knowledge_id: str,
    work_id: str,
    pol_score: float,
    block_accepted: bool,
    *,
    usage_id: str | None = None,
    producer_id: str = "",
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> KnowledgeWorkRecord:
    """Crée un KnowledgeWorkRecord PENDING (pas encore on-chain).

    Args:
        knowledge_id    : KnowledgeID ARTCD source.
        work_id         : WorkID économique (WorkRegistry).
        pol_score       : score PoL calculé par PolScorer [0.0, 1.0].
        block_accepted  : True si pol_score >= IMMUTABLE_POL_THRESHOLD.
        usage_id        : UsageID ARTCD optionnel.
        producer_id     : identifiant de l'agent/wallet producteur.
        metadata        : champs libres optionnels.
        created_at      : timestamp (généré si absent).

    Returns:
        KnowledgeWorkRecord avec status="PENDING" et block_hash=None.
    """
    if not knowledge_id:
        raise ValueError("knowledge_id ne peut pas être vide")
    if not work_id:
        raise ValueError("work_id ne peut pas être vide")
    if not (0.0 <= pol_score <= 1.0):
        raise ValueError(f"pol_score doit être dans [0.0, 1.0], reçu: {pol_score}")

    ts = created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    work_record_id = _compute_work_record_id(
        knowledge_id=knowledge_id,
        work_id=work_id,
        pol_score=pol_score,
        created_at=ts,
    )

    rec = KnowledgeWorkRecord(
        work_record_id=work_record_id,
        knowledge_id=knowledge_id,
        work_id=work_id,
        pol_score=pol_score,
        block_accepted=block_accepted,
        created_at=ts,
        status="PENDING",
        block_hash=None,
        usage_id=usage_id,
        producer_id=producer_id,
        metadata=dict(metadata) if metadata else {},
    )
    logger.debug(
        "create_knowledge_work_record: work_record_id=%s knowledge_id=%s pol_score=%.4f accepted=%s",
        work_record_id, knowledge_id, pol_score, block_accepted,
    )
    return rec


# ── Store persistant ──────────────────────────────────────────────────────────

class KnowledgeWorkStore:
    """Registre JSON atomique des KnowledgeWorkRecords (R436).

    Persistance atomique (R433/R434 pattern : tmp → fsync → rename + fcntl.LOCK_EX).
    Fichier : <data_dir>/knowledge_work_records.json
    """

    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "knowledge_work_records.json"
        if not self._path.is_file():
            self._write_atomic([])

    # ── Verrou transactionnel ─────────────────────────────────────────────────

    @staticmethod
    @contextlib.contextmanager
    def _transactional_lock(target: Path):
        """Verrou exclusif POSIX sur <target>.lock (identique à R433/R434)."""
        lock_path = target.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fh = lock_path.open("a")
        try:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
            except (AttributeError, OSError):
                pass
            yield
        finally:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
            except (AttributeError, OSError):
                pass
            lock_fh.close()

    def _write_atomic(self, records: list[dict]) -> None:
        """Écriture atomique tmp → fsync → rename (R433/R434 pattern)."""
        tmp = self._path.with_suffix(".tmp")
        raw = json.dumps(records, indent=2, ensure_ascii=False)
        tmp.write_text(raw, encoding="utf-8")
        try:
            with tmp.open("r") as tmp_fh:
                os.fsync(tmp_fh.fileno())
        except OSError:
            pass
        tmp.replace(self._path)

    def _read(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("KnowledgeWorkStore unreadable: %s — %s", self._path, exc)
            return []

    def save(self, record: KnowledgeWorkRecord) -> None:
        """Ajoute ou met à jour un KnowledgeWorkRecord (upsert par work_record_id)."""
        with self._transactional_lock(self._path):
            rows = self._read()
            rows = [r for r in rows if r.get("work_record_id") != record.work_record_id]
            rows.append(record.to_dict())
            self._write_atomic(rows)
        logger.debug("KnowledgeWorkStore.save: %s status=%s", record.work_record_id, record.status)

    def get(self, work_record_id: str) -> KnowledgeWorkRecord | None:
        """Retourne un KnowledgeWorkRecord par ID, ou None s'il n'existe pas."""
        for row in self._read():
            if row.get("work_record_id") == work_record_id:
                return KnowledgeWorkRecord.from_dict(row)
        return None

    def list_pending(self) -> list[KnowledgeWorkRecord]:
        """Liste les KnowledgeWorkRecords en attente d'inscription on-chain."""
        return [
            KnowledgeWorkRecord.from_dict(r)
            for r in self._read()
            if r.get("status") == "PENDING"
        ]

    def list_sealed(self) -> list[KnowledgeWorkRecord]:
        """Liste les KnowledgeWorkRecords inscrits on-chain (SEALED)."""
        return [
            KnowledgeWorkRecord.from_dict(r)
            for r in self._read()
            if r.get("status") == "SEALED"
        ]

    def list_by_knowledge_id(self, knowledge_id: str) -> list[KnowledgeWorkRecord]:
        """Retourne tous les KnowledgeWorkRecords liés à un KnowledgeID."""
        return [
            KnowledgeWorkRecord.from_dict(r)
            for r in self._read()
            if r.get("knowledge_id") == knowledge_id
        ]

    def seal_with_block_hash(
        self,
        work_record_id: str,
        block_hash: str,
    ) -> KnowledgeWorkRecord:
        """Scelle un KnowledgeWorkRecord PENDING avec le hash du bloc on-chain.

        Seul un record PENDING peut être scellé. Si le record est déjà SEALED
        ou inexistant, lève ValueError.

        Args:
            work_record_id : identifiant du KnowledgeWorkRecord à sceller.
            block_hash     : hash du bloc on-chain (hex ou format natif).

        Returns:
            KnowledgeWorkRecord mis à jour avec status="SEALED".
        """
        with self._transactional_lock(self._path):
            rows = self._read()
            found = None
            for r in rows:
                if r.get("work_record_id") == work_record_id:
                    found = r
                    break
            if found is None:
                raise ValueError(f"KnowledgeWorkRecord introuvable: {work_record_id}")
            if found.get("status") == "SEALED":
                raise ValueError(
                    f"KnowledgeWorkRecord {work_record_id} déjà SEALED "
                    f"(block_hash={found.get('block_hash')})"
                )
            rec = KnowledgeWorkRecord.from_dict(found)
            sealed = rec.seal(block_hash)
            rows = [r for r in rows if r.get("work_record_id") != work_record_id]
            rows.append(sealed.to_dict())
            self._write_atomic(rows)
            logger.info(
                "KnowledgeWorkStore.seal: %s → SEALED block_hash=%s",
                work_record_id, block_hash[:16],
            )
            return sealed
