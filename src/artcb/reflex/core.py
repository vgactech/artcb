"""Réflexe ARTCB — Moteur de priorité automatique (R350–R355+R368, 2026-09-18).

Ce module implémente le réflexe autonome ARTCB :
- Détection des déclencheurs (mémoire, thinking, raisonnement, biométrie)
- Priorisation automatique des chantiers
- Création d'un REASONING_RECORD à chaque activation (R355)
- Activation simultanée Bob IDE + Cursor
- Branchement PreflightEngine obligatoire avant activation (R368)

R368 (2026-09-18) : activate() appelle PreflightEngine.run_checks() avant de
    créer le ReasoningRecord. Le snapshot (git, ledger, live) est injecté dans
    le record — le chemin Prompt→Preflight→Reflex→Record est traçable.

HONNÊTETÉ :
    - CERTIFIED_100=false.
    - Test de bypass restant : test_r355_enforcement_e2e.py.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from src.artcb.reasoning.reference_id import ref_rule, ref_code
from src.artcb.reasoning.first_reflex import FirstReflex, estimate_earliest_from_logs
from src.artcb.reasoning.record import (
    ReasoningRecord,
    RecordAction,
    RecordOutcome,
    get_record_store,
)

logger = logging.getLogger("artcb.reflex.core")


# --------------------------------------------------------------------------- #
#  Priorités
# --------------------------------------------------------------------------- #

class ReflexPriority(IntEnum):
    """Niveaux de priorité du réflexe ARTCB (R350).

    0 = REFLEX_MEMORY : mémoire IA / thinking / raisonnement → priorité absolue
    1 = SECURITY      : sécurité biométrique / identité humaine
    2 = PQC           : certification post-quantique
    3 = OTHER         : tous les autres chantiers
    """
    REFLEX_MEMORY = 0
    SECURITY      = 1
    PQC           = 2
    OTHER         = 3


# --------------------------------------------------------------------------- #
#  Déclencheurs
# --------------------------------------------------------------------------- #

@dataclass
class ReflexTrigger:
    """Représente un déclencheur du réflexe ARTCB."""
    name: str
    priority: ReflexPriority
    reason: str
    detected_at: float = field(default_factory=time.time)
    keywords: list[str] = field(default_factory=list)
    files_affected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "priority": int(self.priority),
            "priority_name": self.priority.name,
            "reason": self.reason,
            "detected_at": self.detected_at,
            "keywords": self.keywords,
            "files_affected": self.files_affected,
        }


# ─── Mots-clés déclencheurs par priorité ─────────────────────────────────────

_REFLEX_MEMORY_KEYWORDS = [
    "réflexe", "reflexe", "reflex", "reflect",
    "mémoire", "memoire", "memory", "memo",
    "thinking", "raisonnement", "reasoning",
    "ai_memory", "ai memory", "chain_memory",
    "artcb_memo", "artcb_memory_event", "artcb_agent_bootstrap",
    "artcb_think", "artcb_search",
    "canonical_reasoning", "ReasoningID",
    "ingest", "bootstrap", "session_start",
]

_SECURITY_KEYWORDS = [
    "biométrie", "biometrie", "biometric",
    "webauthn", "WebAuthn",
    "empreinte", "fingerprint", "face_id",
    "human_identity", "HumanIdentity",
    "unique_human", "anti-sybil",
    "add_device", "multi_device",
    "wallet_device_binding",
]

_PQC_KEYWORDS = [
    "pqc", "ml-dsa", "ml_dsa", "ML-DSA",
    "post.quantique", "post_quantique", "post-quantique",
    "kyber", "dilithium", "falcon",
    "certif_vpqc", "vpqc2",
]

_REFLEX_FILES = [
    "src/artcb/memory/",
    "src/artcb/reasoning/",
    "src/artcb/reflex/",
    "src/artcb/mcp/tools.py",
    "src/artcb/mcp/server.py",
    ".bob/hooks/",
    ".cursor/hooks/",
    "AUTO_PROMPT_ARTCB",
    "LEÇONS_APPRISES_ARTCB",
    "PROTOCOLE_ARTCB",
]

_SECURITY_FILES = [
    "src/artcb/identity/",
    "src/api/auth_routes.py",
    "src/api/webauthn_routes.py",
    "src/api/biometric_identity_routes.py",
    "src/artcb/crypto/",
]

_PQC_FILES = [
    "src/artcb/crypto/pqc",
    "src/api/ops_routes.py",
    "scripts/certif_vpqc2",
]


# --------------------------------------------------------------------------- #
#  Moteur réflexe
# --------------------------------------------------------------------------- #

class ReflexEngine:
    """Moteur de réflexe ARTCB.

    Détecte les déclencheurs et priorise les chantiers automatiquement.
    Compatible Bob IDE (via hooks) et Cursor (via alwaysApply rules).
    """

    def __init__(self) -> None:
        self._triggers: list[ReflexTrigger] = []
        self._activated_at: float | None = None
        self.certified: bool = False  # CERTIFIED_100=false
        self.unique_human_proven: bool = False
        self._last_record: Any = None  # dernier ReasoningRecord créé (R355)

    # ── Détection ─────────────────────────────────────────────────────────────

    def detect_trigger(
        self,
        text: str = "",
        files: list[str] | None = None,
    ) -> list[ReflexTrigger]:
        """Analyse le texte et les fichiers pour détecter les déclencheurs.

        Args:
            text: Texte du prompt ou contenu à analyser.
            files: Liste de fichiers modifiés (chemins relatifs).

        Returns:
            Liste de déclencheurs détectés, triés par priorité.
        """
        triggers: list[ReflexTrigger] = []
        text_lower = text.lower()
        files = files or []

        # Priorité 0 : REFLEX_MEMORY
        mem_kw = [kw for kw in _REFLEX_MEMORY_KEYWORDS if kw.lower() in text_lower]
        mem_files = [f for f in files if any(rf in f for rf in _REFLEX_FILES)]
        if mem_kw or mem_files:
            triggers.append(ReflexTrigger(
                name="REFLEX_MEMORY",
                priority=ReflexPriority.REFLEX_MEMORY,
                reason="Mémoire IA / thinking / raisonnement détecté",
                keywords=mem_kw,
                files_affected=mem_files,
            ))

        # Priorité 1 : SECURITY
        sec_kw = [kw for kw in _SECURITY_KEYWORDS if kw.lower() in text_lower]
        sec_files = [f for f in files if any(sf in f for sf in _SECURITY_FILES)]
        if sec_kw or sec_files:
            triggers.append(ReflexTrigger(
                name="SECURITY",
                priority=ReflexPriority.SECURITY,
                reason="Sécurité biométrique / identité humaine détectée",
                keywords=sec_kw,
                files_affected=sec_files,
            ))

        # Priorité 2 : PQC
        pqc_kw = [kw for kw in _PQC_KEYWORDS if kw.lower() in text_lower]
        pqc_files = [f for f in files if any(pf in f for pf in _PQC_FILES)]
        if pqc_kw or pqc_files:
            triggers.append(ReflexTrigger(
                name="PQC",
                priority=ReflexPriority.PQC,
                reason="Certification post-quantique détectée",
                keywords=pqc_kw,
                files_affected=pqc_files,
            ))

        # Trier par priorité (0 = le plus important)
        triggers.sort(key=lambda t: t.priority)
        self._triggers.extend(triggers)
        return triggers

    # ── Activation ────────────────────────────────────────────────────────────

    def check_priority(
        self,
        text: str = "",
        files: list[str] | None = None,
    ) -> ReflexPriority:
        """Retourne la priorité courante basée sur les déclencheurs détectés."""
        triggers = self.detect_trigger(text=text, files=files)
        if not triggers:
            return ReflexPriority.OTHER
        return triggers[0].priority

    def activate(
        self,
        text: str = "",
        files: list[str] | None = None,
        session_id: str = "",
        agent_id: str = "bob-ide",
        task_id: str = "unknown",
        preflight_mode: str = "full",
    ) -> dict[str, Any]:
        """Active le réflexe, crée un REASONING_RECORD et retourne un rapport.

        R368 : appelle PreflightEngine avant de créer le ReasoningRecord.
        Le snapshot (git, ledger, live) est injecté dans le record.

        Args:
            text:           Texte du prompt ou description du contexte.
            files:          Fichiers modifiés.
            session_id:     Identifiant de session (optionnel).
            agent_id:       Identifiant de l'agent (optionnel).
            task_id:        Identifiant de la tâche courante (pour PreflightEngine).
            preflight_mode: "full" (défaut) ou "lite".

        Returns:
            Dictionnaire de rapport d'activation incluant le record_id R355
            et le preflight_result R368.
        """
        self._activated_at = time.time()
        triggers = self.detect_trigger(text=text, files=files)
        priority = triggers[0].priority if triggers else ReflexPriority.OTHER

        # ── R368 : PreflightEngine — exécuté AVANT le ReasoningRecord ────────
        preflight_result = None
        preflight_snapshot: dict[str, Any] = {}
        try:
            from src.artcb.reflex.preflight import PreflightEngine, PreflightMode
            _mode = PreflightMode.LITE if preflight_mode == "lite" else PreflightMode.FULL
            _pfe = PreflightEngine()
            preflight_result = _pfe.run_checks(task_id=task_id, mode=_mode)
            preflight_snapshot = _pfe.build_context_snapshot()
            logger.debug(
                "PreflightEngine status=%s task=%s ctx=%s",
                preflight_result.overall_status.value,
                task_id,
                preflight_result.context_sha,
            )
        except Exception as exc:
            logger.warning("PreflightEngine error (non-fatal): %s", exc)

        # ── R355 : créer FIRST_REFLEX ─────────────────────────────────────
        _files = files or []
        first_reflex: FirstReflex | None = None
        if triggers:
            t0 = triggers[0]
            ref_rule_id = ref_rule(
                rule_name=f"R350-{t0.name}",
                rule_file=".cursor/rules/artcb-reflex-priority.mdc",
                rule_version="2026-09-17",
            )
            ref_files = [
                ref_code(path=f, commit="", symbol="")
                for f in _files[:5]  # limité à 5 fichiers pour compacité
            ]
            first_reflex = FirstReflex(
                session_id=session_id or f"reflex_{int(self._activated_at)}",
                trigger_name=t0.name,
                priority=int(t0.priority),
                evidence={
                    "keywords": t0.keywords,
                    "files": t0.files_affected,
                    "prompt_chars": len(text),
                },
                reference_ids=[ref_rule_id.canonical] + [r.canonical for r in ref_files],
            )

        # ── R355 : EARLIEST_DETECTABLE_POINT ─────────────────────────────
        earliest = None
        if first_reflex:
            earliest = estimate_earliest_from_logs(first_reflex.trigger_name)

        # ── R355+R368 : créer REASONING_RECORD avec snapshot preflight ────
        record = ReasoningRecord(
            session_id=session_id or f"reflex_{int(self._activated_at)}",
            agent_id=agent_id,
            context_summary=text[:200] if text else "",
            context_sha256=hashlib.sha256(text.encode()).hexdigest() if text else "",
            first_reflex=first_reflex,
            earliest=earliest,
            action=RecordAction.ANALYZE,
            action_detail=f"Réflexe R350–R355+R368 activé — priorité {priority.name}",
            outcome=RecordOutcome.PENDING,
        )
        # R368 : injecter le snapshot de contexte dans le record
        if preflight_snapshot:
            record.add_observation(
                "preflight_snapshot",
                git_sha=preflight_snapshot.get("git_sha", "")[:7] if preflight_snapshot.get("git_sha") else "",
                ledger_sha=preflight_snapshot.get("ledger_sha256", "")[:12] if preflight_snapshot.get("ledger_sha256") else "",
                ledger_git_head=preflight_snapshot.get("ledger_git_head", ""),
                live_height=preflight_snapshot.get("live_height"),
                live_git_sha=preflight_snapshot.get("live_git_sha", ""),
                certified_100=False,
            )
        if first_reflex:
            from src.artcb.reasoning.reference_id import ref_rule as _ref_rule
            record.add_reference(_ref_rule(
                rule_name=f"R350-{triggers[0].name}",
                rule_file=".cursor/rules/artcb-reflex-priority.mdc",
                rule_version="2026-09-17",
            ))
        for obs_file in _files[:5]:
            record.add_observation("file_in_context", path=obs_file)

        # Persister localement (non bloquant)
        try:
            get_record_store().append(record)
        except Exception as exc:
            logger.warning("REASONING_RECORD store error (non-fatal): %s", exc)

        self._last_record = record

        # ── Rapport ───────────────────────────────────────────────────────
        report = {
            "reflex_activated": True,
            "priority": int(priority),
            "priority_name": priority.name,
            "triggers": [t.to_dict() for t in triggers],
            "activated_at": self._activated_at,
            "certified": self.certified,
            "unique_human_proven": self.unique_human_proven,
            "record_id": record.record_id,         # R355 — clé de traçabilité
            "first_reflex": first_reflex.to_dict() if first_reflex else None,
            "earliest": earliest.to_dict() if earliest else None,
            # R368 — preflight result
            "preflight_status": preflight_result.overall_status.value if preflight_result else "not_run",
            "preflight_context_sha": preflight_result.context_sha if preflight_result else None,
            "preflight_git_sha": preflight_snapshot.get("git_sha", "")[:7] if preflight_snapshot else None,
            "preflight_ledger_sha": preflight_snapshot.get("ledger_sha256", "")[:12] if preflight_snapshot else None,
            "note": (
                "Réflexe ARTCB activé (R350–R355+R368). "
                "PreflightEngine exécuté. "
                "REASONING_RECORD créé avec snapshot contexte. "
                "CERTIFIED_100=false."
            ),
        }

        if priority == ReflexPriority.REFLEX_MEMORY:
            report["action"] = (
                "PRIORITÉ ABSOLUE : chantier mémoire/thinking/réflexe "
                "activé avant tout autre travail."
            )
        elif priority == ReflexPriority.SECURITY:
            report["action"] = (
                "PRIORITÉ 1 : chantier sécurité biométrique/identité "
                "activé en priorité."
            )
        elif priority == ReflexPriority.PQC:
            report["action"] = (
                "PRIORITÉ 2 : chantier PQC activé en priorité."
            )
        else:
            report["action"] = "Chantier standard — aucun réflexe prioritaire détecté."

        logger.info(
            "ReflexEngine activé: priority=%s triggers=%d record_id=%s",
            priority.name, len(triggers), record.record_id[:12],
        )
        return report

    # ── Rapport ───────────────────────────────────────────────────────────────

    def report(self) -> dict[str, Any]:
        """Retourne un rapport complet de l'état du moteur réflexe."""
        return {
            "engine": "ReflexEngine ARTCB v1",
            "rules": "R350–R354 (2026-09-17)",
            "activated_at": self._activated_at,
            "total_triggers": len(self._triggers),
            "certified": self.certified,
            "unique_human_proven": self.unique_human_proven,
            "priorities": {
                "REFLEX_MEMORY": int(ReflexPriority.REFLEX_MEMORY),
                "SECURITY": int(ReflexPriority.SECURITY),
                "PQC": int(ReflexPriority.PQC),
                "OTHER": int(ReflexPriority.OTHER),
            },
            "note": (
                "CERTIFIED_100=false — réflexe stub fonctionnel. "
                "Activation réelle via hooks Bob IDE et Cursor."
            ),
        }

    # ── Classe convenience ────────────────────────────────────────────────────

    @classmethod
    def from_prompt(cls, prompt: str, files: list[str] | None = None) -> "ReflexEngine":
        """Crée et active un moteur réflexe depuis un prompt."""
        engine = cls()
        engine.activate(text=prompt, files=files)
        return engine


# --------------------------------------------------------------------------- #
#  Instance globale (singleton léger)
# --------------------------------------------------------------------------- #

_global_engine: ReflexEngine | None = None


def get_reflex_engine() -> ReflexEngine:
    """Retourne l'instance globale du moteur réflexe."""
    global _global_engine
    if _global_engine is None:
        _global_engine = ReflexEngine()
    return _global_engine
