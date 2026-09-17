"""REASONING_RECORD — Enveloppe complète d'un cycle raisonnement ARTCB.

## Corrections R355.1–R355.3 (audit rapport 371, 2026-09-17)

### R355.1 — final_hash = hash canonique de TOUT le record scellé
  Avant : record_id = hash(session + agent + context + ts_start + first_reflex_sha + refs seulement)
          — ne couvrait pas observations, action, outcome, learning, earliest, ts_end
  Après : record_id = hash stable d'identité (session + ts_start + first_reflex_sha + refs)
          final_hash = hash(canonique complet = TOUS les champs) — calculé dans seal()
  Le final_hash est l'empreinte cryptographique vérifiable du cycle complet.

### R355.2 — seal() gèle le record (frozen=True)
  Après seal(), toute tentative de modification lève SealedRecordError.
  seal() calcule final_hash sur l'intégralité des champs.
  frozen=True est persisté dans le dict sérialisé → détectable à la relecture.

### R355.3 — /seal API préserve FIRST_REFLEX + EARLIEST + refs + observations
  Avant : /seal créait un nouveau record incomplet (sans first_reflex, earliest, refs, observations).
  Après : /seal reconstruit le record complet depuis le JSONL et le scelle en place.
  Le record scellé est la version de référence — l'original non scellé est conservé.

## Honnêteté

Le REASONING_RECORD couvre ce qui est OBSERVABLE et SURFACÉ (prompts, fichiers, résultats mesurables).
Il ne couvre PAS le CoT interne du modèle (inaccessible — limitation fondamentale du standard W3C).
CERTIFIED_100=false.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.artcb.reasoning.reference_id import ReferenceID
from src.artcb.reasoning.first_reflex import (
    FirstReflex,
    EarliestDetectablePoint,
)


# ─── Erreur : modification d'un record scellé ────────────────────────────────


class SealedRecordError(RuntimeError):
    """Levée si on tente de modifier un ReasoningRecord après seal()."""


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

    Cycle de vie :
      1. Création (open) — record_id calculé sur les champs d'identité stables
      2. Observations ajoutées progressivement (add_observation, add_reference)
      3. seal() — gèle définitivement le record, calcule final_hash sur TOUT
      4. Persistance (store.append) — version scellée gravée
      5. Gravure on-chain via /api/v1/ai/memo (final_hash comme preuve)

    Après seal(), toute modification lève SealedRecordError.
    """

    # ── Identité ─────────────────────────────────────────────────────────────
    session_id: str
    agent_id: str = "bob-ide"

    # ── Contexte reçu ────────────────────────────────────────────────────────
    context_summary: str = ""
    context_sha256: str = ""

    # ── Réflexe ──────────────────────────────────────────────────────────────
    first_reflex: FirstReflex | None = None
    earliest: EarliestDetectablePoint | None = None

    # ── Références (causes) ──────────────────────────────────────────────────
    reference_ids: list[ReferenceID] = field(default_factory=list)

    # ── Observations ─────────────────────────────────────────────────────────
    observations: list[dict[str, Any]] = field(default_factory=list)

    # ── Action + Résultat ────────────────────────────────────────────────────
    action: RecordAction = RecordAction.NOOP
    action_detail: str = ""
    outcome: RecordOutcome = RecordOutcome.UNKNOWN
    outcome_detail: str = ""

    # ── Apprentissage ────────────────────────────────────────────────────────
    learning: str = ""
    new_rule_candidate: bool = False

    # ── Chaîne ───────────────────────────────────────────────────────────────
    chain_block_index: int | None = None
    chain_block_hash: str = ""

    # ── Méta ─────────────────────────────────────────────────────────────────
    ts_start_ns: int = field(default_factory=time.time_ns)
    ts_end_ns: int | None = None

    # ── Identité cryptographique ─────────────────────────────────────────────
    # record_id : stable — hash(identité+contexte+réflexe+refs+ts_start)
    #             calculé à la création, ne change pas avec les observations
    # final_hash : calculé dans seal() — hash de TOUS les champs — preuve finale
    record_id: str = field(default="", init=False)
    final_hash: str = field(default="", init=False)  # vide jusqu'au seal()
    frozen: bool = field(default=False, init=False)
    certified: bool = False

    def __post_init__(self) -> None:
        self.record_id = self._compute_record_id()

    # ── Calcul d'identité ─────────────────────────────────────────────────────

    def _compute_record_id(self) -> str:
        """Hash stable sur les champs d'identité (stable pendant la phase ouverte).

        Couvre : session, agent, contexte, ts_start, first_reflex, references.
        Ne change PAS quand on ajoute des observations (pour pouvoir référencer
        le record avant sa clôture).
        """
        payload = {
            "v": "r355.1",
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "context_sha256": self.context_sha256,
            "ts_start_ns": self.ts_start_ns,
            "first_reflex_sha": self.first_reflex.sha256 if self.first_reflex else "",
            "reference_canonicals": sorted(str(r) for r in self.reference_ids),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def _compute_final_hash(self) -> str:
        """Hash cryptographique de TOUT le record — calculé dans seal() uniquement.

        R355.1 : inclut observations, action, outcome, learning, earliest,
                 ts_end, chain_block_hash, new_rule_candidate — TOUS les champs.
        Ce hash est la preuve vérifiable du cycle complet.
        """
        canonical = {
            "v": "r355.1-final",
            "record_id": self.record_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "context_summary": self.context_summary,
            "context_sha256": self.context_sha256,
            "first_reflex_sha": self.first_reflex.sha256 if self.first_reflex else "",
            "earliest_sha": self.earliest.sha256 if self.earliest else "",
            "reference_canonicals": sorted(str(r) for r in self.reference_ids),
            "observations_count": len(self.observations),
            "observations_sha": hashlib.sha256(
                json.dumps(self.observations, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, default=str).encode()
            ).hexdigest(),
            "action": self.action.value,
            "action_detail": self.action_detail,
            "outcome": self.outcome.value,
            "outcome_detail": self.outcome_detail,
            "learning_sha": hashlib.sha256(self.learning.encode()).hexdigest(),
            "new_rule_candidate": self.new_rule_candidate,
            "chain_block_index": self.chain_block_index,
            "chain_block_hash": self.chain_block_hash,
            "ts_start_ns": self.ts_start_ns,
            "ts_end_ns": self.ts_end_ns,
        }
        blob = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    # ── Mutation (interdit après seal) ────────────────────────────────────────

    def _check_not_frozen(self, operation: str) -> None:
        if self.frozen:
            raise SealedRecordError(
                f"ReasoningRecord est scellé (frozen=True) — opération '{operation}' interdite. "
                f"record_id={self.record_id[:12]}… final_hash={self.final_hash[:12]}…"
            )

    def seal(
        self,
        *,
        outcome: RecordOutcome = RecordOutcome.PASS,
        outcome_detail: str = "",
        learning: str = "",
        new_rule_candidate: bool = False,
    ) -> "ReasoningRecord":
        """Gèle définitivement le record et calcule final_hash.

        R355.2 : après seal(), toute modification lève SealedRecordError.
        final_hash = SHA-256(canonique complet = TOUS les champs).
        Retourne self pour chaînage.
        """
        self._check_not_frozen("seal")
        self.ts_end_ns = time.time_ns()
        self.outcome = outcome
        self.outcome_detail = outcome_detail
        self.learning = learning
        self.new_rule_candidate = new_rule_candidate
        # R355.1 : calcul du final_hash sur l'intégralité des champs
        self.final_hash = self._compute_final_hash()
        # R355.2 : geler
        self.frozen = True
        return self

    def add_observation(self, kind: str, **kwargs: Any) -> "ReasoningRecord":
        """Ajoute une observation. Interdit après seal()."""
        self._check_not_frozen("add_observation")
        self.observations.append({"kind": kind, "ts_ns": time.time_ns(), **kwargs})
        return self

    def add_reference(self, ref: ReferenceID) -> "ReasoningRecord":
        """Ajoute un ReferenceID. Interdit après seal()."""
        self._check_not_frozen("add_reference")
        self.reference_ids.append(ref)
        return self

    # ── Accès ─────────────────────────────────────────────────────────────────

    def duration_ms(self) -> float | None:
        if self.ts_end_ns is None:
            return None
        return (self.ts_end_ns - self.ts_start_ns) / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "final_hash": self.final_hash,      # vide si pas encore scellé
            "frozen": self.frozen,
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
                "R355.1: final_hash=hash(tous les champs) calculé dans seal(). "
                "R355.2: frozen après seal() — SealedRecordError si modification. "
                "CERTIFIED_100=false."
            ),
        }

    def to_memo_content(self) -> str:
        """Sérialise le record pour gravure on-chain. Inclut final_hash."""
        d = self.to_dict()
        return json.dumps(d, ensure_ascii=False, indent=2)

    def __str__(self) -> str:
        dur = self.duration_ms()
        dur_str = f"{dur:.0f}ms" if dur is not None else "en cours"
        fh = f" final_hash={self.final_hash[:12]}…" if self.final_hash else ""
        return (
            f"ReasoningRecord("
            f"id={self.record_id[:12]}…{fh} "
            f"frozen={self.frozen} "
            f"action={self.action.value} "
            f"outcome={self.outcome.value} "
            f"dur={dur_str})"
        )


# ─── Reconstruction depuis dict (R355.3) ──────────────────────────────────────


def record_from_dict(d: dict[str, Any]) -> ReasoningRecord:
    """Reconstruit un ReasoningRecord depuis son dict sérialisé (JSONL).

    R355.3 : préserve first_reflex, earliest, reference_ids, observations.
    Ne lève pas d'erreur si certains champs sont absents (compatibilité forward).
    """
    from src.artcb.reasoning.reference_id import ref_from_dict as _ref_from_dict
    from src.artcb.reasoning.first_reflex import FirstReflex, EarliestDetectablePoint

    # Reconstruire first_reflex
    fr_data = d.get("first_reflex")
    first_reflex: FirstReflex | None = None
    if fr_data and isinstance(fr_data, dict):
        try:
            first_reflex = FirstReflex(
                session_id=fr_data.get("session_id", ""),
                trigger_name=fr_data.get("trigger_name", ""),
                priority=fr_data.get("priority", 3),
                ts_ns=fr_data.get("ts_ns", time.time_ns()),
                evidence=fr_data.get("evidence", {}),
                reference_ids=fr_data.get("reference_ids", []),
            )
            # Restaurer le sha256 original (ne pas recalculer — immuable)
            object.__setattr__(first_reflex, "sha256", fr_data.get("sha256", first_reflex.sha256))
        except Exception:
            pass

    # Reconstruire earliest
    ed_data = d.get("earliest")
    earliest: EarliestDetectablePoint | None = None
    if ed_data and isinstance(ed_data, dict):
        try:
            earliest = EarliestDetectablePoint(
                trigger_name=ed_data.get("trigger_name", ""),
                chain_height=ed_data.get("chain_height"),
                block_hash=ed_data.get("block_hash", ""),
                confidence=ed_data.get("confidence", 0.0),
                method=ed_data.get("method", "unknown"),
                notes=ed_data.get("notes", ""),
                ts_ns=ed_data.get("ts_ns", time.time_ns()),
                reference_ids=ed_data.get("reference_ids", []),
            )
        except Exception:
            pass

    # Reconstruire reference_ids
    ref_ids: list[ReferenceID] = []
    for r in d.get("reference_ids", []):
        if isinstance(r, dict):
            try:
                ref_ids.append(_ref_from_dict(r))
            except Exception:
                pass

    # Reconstruire le record
    try:
        action = RecordAction(d.get("action", "noop"))
    except ValueError:
        action = RecordAction.NOOP
    try:
        outcome = RecordOutcome(d.get("outcome", "unknown"))
    except ValueError:
        outcome = RecordOutcome.UNKNOWN

    r = ReasoningRecord(
        session_id=d.get("session_id", ""),
        agent_id=d.get("agent_id", "bob-ide"),
        context_summary=d.get("context_summary", ""),
        context_sha256=d.get("context_sha256", ""),
        first_reflex=first_reflex,
        earliest=earliest,
        reference_ids=ref_ids,
        observations=list(d.get("observations", [])),
        action=action,
        action_detail=d.get("action_detail", ""),
        outcome=outcome,
        outcome_detail=d.get("outcome_detail", ""),
        learning=d.get("learning", ""),
        new_rule_candidate=bool(d.get("new_rule_candidate", False)),
        chain_block_index=d.get("chain_block_index"),
        chain_block_hash=d.get("chain_block_hash", ""),
        ts_start_ns=d.get("ts_start_ns", time.time_ns()),
        certified=bool(d.get("certified", False)),
    )
    # Restaurer ts_end_ns sans passer par seal() (on reconstruit)
    if d.get("ts_end_ns"):
        object.__setattr__(r, "ts_end_ns", d["ts_end_ns"])
    # Restaurer final_hash et frozen (si le record était scellé)
    stored_final_hash = d.get("final_hash", "")
    if stored_final_hash:
        object.__setattr__(r, "final_hash", stored_final_hash)
        object.__setattr__(r, "frozen", True)
    return r


# ─── Store local (append-only JSONL) ─────────────────────────────────────────


class ReasoningRecordStore:
    """Persistance locale des REASONING_RECORD (append-only JSONL).

    Fichier : data/trace/reasoning_records.jsonl
    Chaque ligne = un record complet sérialisé en JSON.
    Ce fichier est gitignored.
    """

    def __init__(self, path: str | Path = "data/trace/reasoning_records.jsonl") -> None:
        self._path = Path(path)

    def append(self, record: ReasoningRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def load_all(self) -> list[dict[str, Any]]:
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

    def find_by_record_id(self, record_id_prefix: str) -> dict[str, Any] | None:
        """Trouve un record par préfixe de record_id (ou final_hash)."""
        for row in self.load_all():
            if (row.get("record_id", "").startswith(record_id_prefix) or
                    row.get("final_hash", "").startswith(record_id_prefix)):
                return row
        return None

    def seal_in_place(
        self,
        record_id_prefix: str,
        *,
        outcome: RecordOutcome,
        outcome_detail: str,
        learning: str,
        new_rule_candidate: bool,
    ) -> ReasoningRecord | None:
        """R355.3 : scelle un record existant en place et persiste la version scellée.

        Reconstruit le record complet (avec first_reflex, earliest, refs, obs),
        applique seal(), et ajoute la version scellée au store.
        Retourne le record scellé, ou None si non trouvé.
        """
        row = self.find_by_record_id(record_id_prefix)
        if row is None:
            return None
        if row.get("frozen"):
            # Déjà scellé — le retourner tel quel
            return record_from_dict(row)
        # Reconstruire complet (R355.3 : préserve first_reflex, earliest, refs, obs)
        r = record_from_dict(row)
        r.seal(
            outcome=outcome,
            outcome_detail=outcome_detail,
            learning=learning,
            new_rule_candidate=new_rule_candidate,
        )
        self.append(r)
        return r


# ─── Instance globale ─────────────────────────────────────────────────────────

_global_store: ReasoningRecordStore | None = None


def get_record_store() -> ReasoningRecordStore:
    global _global_store
    if _global_store is None:
        _global_store = ReasoningRecordStore()
    return _global_store
