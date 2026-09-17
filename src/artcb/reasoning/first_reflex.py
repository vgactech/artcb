"""FIRST_REFLEX + EARLIEST_DETECTABLE_POINT — Traçabilité temporelle du réflexe ARTCB.

R355 — 2026-09-17.

## Concepts (rapport 370, sections 3 et 7)

### FIRST_REFLEX
Le **premier point temporel** où l'agent a détecté un déclencheur réflexe
dans une session donnée. Répond à la question :
  « Quand l'agent a-t-il RÉELLEMENT pris conscience du problème ? »

Champs obligatoires :
  - ts_ns          : horodatage nanoseconde (time.time_ns)
  - session_id     : identifiant de session
  - trigger_name   : nom du déclencheur (REFLEX_MEMORY / SECURITY / PQC / OTHER)
  - priority       : niveau de priorité (0/1/2/3)
  - evidence       : liste des preuves (mots-clés détectés, fichiers)
  - reference_ids  : liste de ReferenceID pointant les causes
  - sha256         : hash du contexte de détection

### EARLIEST_DETECTABLE_POINT
La **rétroprojection** : à quelle hauteur de chaîne aurait-on pu / dû
détecter le problème si le réflexe avait été actif plus tôt.
Répond à la question :
  « Ce problème existait-il avant qu'on le détecte ? »

Champs obligatoires :
  - chain_height     : hauteur de bloc estimée
  - block_hash       : hash du bloc estimé (peut être vide)
  - confidence       : confiance de la rétroprojection (0.0–1.0)
  - method           : comment on a estimé (keyword_history / log_trace / chain_scan)
  - notes            : explication libre

HONNÊTETÉ : EARLIEST_DETECTABLE_POINT est une estimation.
Elle ne prouve pas que l'agent aurait agi. CERTIFIED_100=false.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from src.artcb.reasoning.reference_id import ReferenceID


# ─── FIRST_REFLEX ─────────────────────────────────────────────────────────────


@dataclass
class FirstReflex:
    """Premier point de détection d'un déclencheur réflexe dans une session.

    Créé par ReflexEngine lors de la première activation d'un trigger donné.
    Immutable après création (la première détection ne change pas).
    """
    session_id: str
    trigger_name: str                        # REFLEX_MEMORY / SECURITY / PQC / OTHER
    priority: int                            # 0 = REFLEX_MEMORY (absolu)
    ts_ns: int = field(default_factory=time.time_ns)
    evidence: dict[str, Any] = field(default_factory=dict)
    # evidence = {"keywords": [...], "files": [...], "prompt_chars": N}
    reference_ids: list[str] = field(default_factory=list)
    # liste de canonical strings ("refid:code:xxx", "refid:rule:xxx"…)
    sha256: str = field(default="", init=False)
    certified: bool = False                  # CERTIFIED_100=false toujours

    def __post_init__(self) -> None:
        self.sha256 = self._compute_hash()

    def _compute_hash(self) -> str:
        blob = json.dumps(
            {
                "session_id": self.session_id,
                "trigger_name": self.trigger_name,
                "priority": self.priority,
                "ts_ns": self.ts_ns,
                "evidence": self.evidence,
                "reference_ids": sorted(self.reference_ids),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "trigger_name": self.trigger_name,
            "priority": self.priority,
            "ts_ns": self.ts_ns,
            "evidence": self.evidence,
            "reference_ids": self.reference_ids,
            "sha256": self.sha256,
            "certified": self.certified,
            "note": "FIRST_REFLEX — premier point de détection dans cette session. CERTIFIED_100=false.",
        }

    def __str__(self) -> str:
        return (
            f"FIRST_REFLEX(session={self.session_id!r} "
            f"trigger={self.trigger_name} prio={self.priority} "
            f"ts_ns={self.ts_ns})"
        )


# ─── EARLIEST_DETECTABLE_POINT ────────────────────────────────────────────────


class EarliestDetectableMethod(str):
    """Méthode d'estimation de EARLIEST_DETECTABLE_POINT."""
    KEYWORD_HISTORY = "keyword_history"   # scan des memos/logs pour les mots-clés
    LOG_TRACE       = "log_trace"         # trace agent_reasoning.jsonl
    CHAIN_SCAN      = "chain_scan"        # scan des blocs on-chain
    MANUAL          = "manual"            # estimation manuelle par l'opérateur
    UNKNOWN         = "unknown"


@dataclass
class EarliestDetectablePoint:
    """Rétroprojection : à quel bloc/moment le problème était déjà présent.

    NE garantit pas que l'agent aurait agi. C'est une estimation.
    CERTIFIED_100=false.
    """
    trigger_name: str
    chain_height: int | None = None          # hauteur de bloc estimée
    block_hash: str = ""                     # hash du bloc estimé
    confidence: float = 0.0                  # 0.0 = inconnue, 1.0 = certaine
    method: str = EarliestDetectableMethod.UNKNOWN
    notes: str = ""
    ts_ns: int = field(default_factory=time.time_ns)
    reference_ids: list[str] = field(default_factory=list)
    sha256: str = field(default="", init=False)
    certified: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence doit être dans [0.0, 1.0], reçu {self.confidence}")
        self.sha256 = self._compute_hash()

    def _compute_hash(self) -> str:
        blob = json.dumps(
            {
                "trigger_name": self.trigger_name,
                "chain_height": self.chain_height,
                "block_hash": self.block_hash,
                "confidence": self.confidence,
                "method": self.method,
                "ts_ns": self.ts_ns,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_name": self.trigger_name,
            "chain_height": self.chain_height,
            "block_hash": self.block_hash,
            "confidence": self.confidence,
            "method": self.method,
            "notes": self.notes,
            "ts_ns": self.ts_ns,
            "reference_ids": self.reference_ids,
            "sha256": self.sha256,
            "certified": self.certified,
            "note": (
                "EARLIEST_DETECTABLE_POINT — estimation rétroprojective. "
                "Ne prouve pas qu'une action aurait été prise. CERTIFIED_100=false."
            ),
        }

    def __str__(self) -> str:
        h = self.chain_height
        c = f"{self.confidence:.0%}"
        return (
            f"EarliestDetectablePoint(trigger={self.trigger_name} "
            f"height={h} confidence={c} method={self.method})"
        )


# ─── Utilitaire : estimer EARLIEST depuis les logs locaux ────────────────────


def estimate_earliest_from_logs(
    trigger_name: str,
    *,
    chain_height_now: int | None = None,
    log_path: str = "data/trace/agent_reasoning.jsonl",
) -> EarliestDetectablePoint:
    """Estime EARLIEST_DETECTABLE_POINT en scannant agent_reasoning.jsonl.

    Cherche la première occurrence des mots-clés du trigger dans les logs.
    Retourne une estimation avec confidence ≤ 0.5 (logs locaux ≠ preuve complète).
    CERTIFIED_100=false.
    """
    import re
    from pathlib import Path

    # Mots-clés par trigger (doit rester synchronisé avec ReflexEngine._*_KEYWORDS)
    _KEYWORDS: dict[str, list[str]] = {
        "REFLEX_MEMORY": ["réflexe", "reflexe", "reflex", "mémoire", "memoire",
                          "thinking", "raisonnement", "ai_memory", "bootstrap"],
        "SECURITY":      ["biométrie", "biometric", "webauthn", "human_identity",
                          "add_device", "unique_human"],
        "PQC":           ["pqc", "ml-dsa", "post-quantique", "certif_vpqc", "vpqc2"],
        "OTHER":         [],
    }
    kws = _KEYWORDS.get(trigger_name, [])

    p = Path(log_path)
    if not p.exists() or not kws:
        return EarliestDetectablePoint(
            trigger_name=trigger_name,
            chain_height=chain_height_now,
            confidence=0.0,
            method=EarliestDetectableMethod.UNKNOWN,
            notes="Log absent ou aucun mot-clé pour ce trigger.",
        )

    first_ts: int | None = None
    matched_line = ""
    try:
        for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            lower = raw.lower()
            if any(kw.lower() in lower for kw in kws):
                try:
                    row = json.loads(raw)
                    ts = row.get("ts_ns")
                    if isinstance(ts, int) and (first_ts is None or ts < first_ts):
                        first_ts = ts
                        matched_line = raw[:120]
                except Exception:
                    pass
    except OSError:
        pass

    if first_ts is None:
        return EarliestDetectablePoint(
            trigger_name=trigger_name,
            chain_height=chain_height_now,
            confidence=0.1,
            method=EarliestDetectableMethod.LOG_TRACE,
            notes="Aucune occurrence trouvée dans les logs locaux.",
        )

    return EarliestDetectablePoint(
        trigger_name=trigger_name,
        chain_height=chain_height_now,
        confidence=0.35,   # logs locaux = partiel — pas une preuve complète
        method=EarliestDetectableMethod.LOG_TRACE,
        notes=(
            f"Première occurrence trouvée dans {log_path}. "
            f"ts_ns={first_ts}. "
            f"Ligne: {matched_line!r}. "
            "CERTIFIED_100=false — estimation log-trace uniquement."
        ),
    )
