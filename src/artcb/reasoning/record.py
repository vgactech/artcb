"""REASONING_RECORD — Enveloppe complète d'un cycle raisonnement ARTCB (R355, 2026-09-17).

## Concept (rapport 370, sections 2–8)

Un REASONING_RECORD est la trace complète d'un cycle agent :

  CONTEXTE REÇU
       │
       ▼
  FIRST_REFLEX (détection)
       │
       ▼
  OBSERVATIONS (preuves)
       │
       ▼
  ACTION (ce que l'agent a fait)
       │
       ▼
  RÉSULTAT (mesurable)
       │
       ▼
  EARLIEST_DETECTABLE_POINT (rétroprojection)
       │
       ▼
  LEARNING (nouvelle règle candidate)
       │
       ▼
  BLOC ON-CHAIN (gravé via /ai/memo)

## Identités dans un REASONING_RECORD

  - record_id   : SHA-256 de l'ensemble (canonical, append-only)
  - session_id  : identifiant de session agent
  - ReasoningID : identifiant du graphe de raisonnement (src/artcb/reasoning/canonical.py)
  - reference_ids : liste de ReferenceID (causes)
  - first_reflex  : FIRST_REFLEX correspondant
  - earliest      : EARLIEST_DETECTABLE_POINT correspondant

## Honnêteté

Le REASONING_RECORD couvre ce qui est OBSERVABLE et SURFACÉ :
  - Prompts reçus
  - Fichiers modifiés
  - Actions exécutées (outils appelés)
  - Memos gravés on-chain
Il ne couvre PAS le CoT interne du modèle (inaccessible).
CERTIFIED_100=false.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.artcb.reasoning.reference_id import ReferenceID
from src.artcb.reasoning.first_reflex import (
    FirstReflex,
    EarliestDetectablePoint,
    estimate_earliest_from_logs,
)


# ─── Types d'actions ─────────────────────────────────────────────────────────


class RecordAction(str, Enum):
    """Type d'action entreprise dans un REASONING_RECORD."""
    IMPLEMENT   = "implement"    # code écrit / modifié
    DEPLOY      = "deploy"       # déploiement live
    TEST        = "test"         # tests lancés
    MEMO        = "memo"         # mémo gravé on-chain
    ANALYZE     = "analyze"      # analyse / audit
    REPAIR      = "repair"       # correction d'un bug
    DEFER       = "defer"        # différé pour plus tard
    NOOP        = "noop"         # aucune action (réflexe non traité)


class RecordOutcome(str, Enum):
    """Résultat d'un REASONING_RECORD."""
    PASS        = "pass"         # action réalisée avec succès
    FAIL        = "fail"         # action échouée
    PARTIAL     = "partial"      # action partiellement réalisée
    PENDING     = "pending"      # en cours
    SKIPPED     = "skipped"      # skipped (non prioritaire)
    UNKNOWN     = "unknown"


# ─── REASONING_RECORD ────────────────────────────────────────────────────────


@dataclass
class ReasoningRecord:
    """Enveloppe complète d'un cycle raisonnement ARTCB.

    Un record est créé à chaque activation du ReflexEngine et lié à une session.
    Il est gravé on-chain via /api/v1/ai/memo après complétion.
    """

    # ── Identité ─────────────────────────────────────────────────────────────
    session_id: str
    agent_id: str = "bob-ide"

    # ── Contexte reçu ────────────────────────────────────────────────────────
    context_summary: str = ""         # résumé du prompt / contexte reçu
    context_sha256: str = ""          # hash du contexte complet (si disponible)

    # ── Réflexe ──────────────────────────────────────────────────────────────
    first_reflex: FirstReflex | None = None
    earliest: EarliestDetectablePoint | None = None

    # ── Références (causes) ──────────────────────────────────────────────────
    reference_ids: list[ReferenceID] = field(default_factory=list)

    # ── Observations ─────────────────────────────────────────────────────────
    observations: list[dict[str, Any]] = field(default_factory=list)
    # [{kind: "file_modified", path: "...", sha256: "..."}, ...]

    # ── Action + Résultat ────────────────────────────────────────────────────
    action: RecordAction = RecordAction.NOOP
    action_detail: str = ""           # description libre de l'action
    outcome: RecordOutcome = RecordOutcome.UNKNOWN
    outcome_detail: str = ""          # mesure live (ex: "3/3 tests PASS")

    # ── Apprentissage ────────────────────────────────────────────────────────
    learning: str = ""                # nouvelle règle candidate (texte libre)
    new_rule_candidate: bool = False  # faut-il créer une règle ?

    # ── Chaîne ───────────────────────────────────────────────────────────────
    chain_block_index: int | None = None   # bloc on-chain après gravure
    chain_block_hash: str = ""

    # ── Méta ─────────────────────────────────────────────────────────────────
    ts_start_ns: int = field(default_factory=time.time_ns)
    ts_end_ns: int | None = None
    record_id: str = field(default="", init=False)
    certified: bool = False           # CERTIFIED_100=false

    def __post_init__(self) -> None:
        self.record_id = self._compute_id()

    def _compute_id(self) -> str:
        payload = {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "context_sha256": self.context_sha256,
            "ts_start_ns": self.ts_start_ns,
            "first_reflex_sha": self.first_reflex.sha256 if self.first_reflex else "",
            "reference_canonicals": sorted(str(r) for r in self.reference_ids),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def seal(
        self,
        *,
        outcome: RecordOutcome = RecordOutcome.PASS,
        outcome_detail: str = "",
        learning: str = "",
        new_rule_candidate: bool = False,
    ) -> "ReasoningRecord":
        """Clôture le record : horodatage de fin + résultat final.

        Doit être appelé quand l'action est terminée, avant gravure on-chain.
        Retourne self pour chaînage.
        """
        self.ts_end_ns = time.time_ns()
        self.outcome = outcome
        self.outcome_detail = outcome_detail
        self.learning = learning
        self.new_rule_candidate = new_rule_candidate
        # Recalcule l'ID car le record a changé
        self.record_id = self._compute_id()
        return self

    def add_observation(
        self,
        kind: str,
        **kwargs: Any,
    ) -> "ReasoningRecord":
        """Ajoute une observation au record.

        Ex: .add_observation("file_modified", path="src/artcb/reflex/core.py", sha256="…")
        Ex: .add_observation("test_result", test="test_reflex", pass_count=5, total=5)
        Ex: .add_observation("api_call", method="POST", url="/api/v1/ai/memo", status=200)
        """
        self.observations.append({"kind": kind, "ts_ns": time.time_ns(), **kwargs})
        return self

    def add_reference(self, ref: ReferenceID) -> "ReasoningRecord":
        """Ajoute un ReferenceID au record."""
        self.reference_ids.append(ref)
        return self

    def duration_ms(self) -> float | None:
        """Durée du cycle en millisecondes (None si pas encore clôturé)."""
        if self.ts_end_ns is None:
            return None
        return (self.ts_end_ns - self.ts_start_ns) / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "context_summary": self.context_summary,
            "context_sha256": self.context_sha256,
            "first_reflex": self.first_reflex.to_dict() if self.first_reflex else None,
            "earliest": self.earliest.to_dict() if self.earliest else None,
            "reference_ids": [r.to_dict() for r in self.reference_ids],
            "observations": self.observations,
            "action": self.action.value,
            "action_detail": self.action_detail,
            "outcome": self.outcome.value,
            "outcome_detail": self.outcome_detail,
            "learning": self.learning,
            "new_rule_candidate": self.new_rule_candidate,
            "chain_block_index": self.chain_block_index,
            "chain_block_hash": self.chain_block_hash,
            "ts_start_ns": self.ts_start_ns,
            "ts_end_ns": self.ts_end_ns,
            "duration_ms": self.duration_ms(),
            "certified": self.certified,
            "note": (
                "REASONING_RECORD — trace complète d'un cycle raisonnement ARTCB. "
                "CERTIFIED_100=false. "
                "Couvre le contexte surfacé, pas le CoT interne du modèle."
            ),
        }

    def to_memo_content(self) -> str:
        """Sérialise le record en texte pour gravure on-chain via /api/v1/ai/memo."""
        d = self.to_dict()
        return json.dumps(d, ensure_ascii=False, indent=2)

    def __str__(self) -> str:
        dur = self.duration_ms()
        dur_str = f"{dur:.0f}ms" if dur is not None else "en cours"
        return (
            f"ReasoningRecord("
            f"id={self.record_id[:12]}… "
            f"session={self.session_id!r} "
            f"action={self.action.value} "
            f"outcome={self.outcome.value} "
            f"dur={dur_str})"
        )


# ─── Store local (append-only JSONL) ─────────────────────────────────────────


class ReasoningRecordStore:
    """Persistance locale des REASONING_RECORD (append-only JSONL).

    Fichier : data/trace/reasoning_records.jsonl
    Chaque ligne = un record complet sérialisé en JSON.
    Ce fichier est gitignored (données locales, pas secrets).
    """

    def __init__(self, path: str | Path = "data/trace/reasoning_records.jsonl") -> None:
        self._path = Path(path)

    def append(self, record: ReasoningRecord) -> None:
        """Persiste un record (append-only, thread-unsafe)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def load_all(self) -> list[dict[str, Any]]:
        """Charge tous les records du fichier local."""
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for raw in self._path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip()
            if raw:
                try:
                    rows.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
        return rows

    def load_by_session(self, session_id: str) -> list[dict[str, Any]]:
        return [r for r in self.load_all() if r.get("session_id") == session_id]

    def count(self) -> int:
        return len(self.load_all())


# ─── Instance globale ─────────────────────────────────────────────────────────

_global_store: ReasoningRecordStore | None = None


def get_record_store() -> ReasoningRecordStore:
    """Retourne l'instance globale du store."""
    global _global_store
    if _global_store is None:
        _global_store = ReasoningRecordStore()
    return _global_store
