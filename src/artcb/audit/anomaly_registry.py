"""Registre canonique des anomalies — R484 / ORDRE 11 (R481) — 2026-09-26.

Transforme les findings dispersés (UAP, UPF, tests, forensic) en objets
persistants structurés avec cycle de vie complet.

Machine d'état (ORDRE 9 — R481) :
    OPEN → IN_PROGRESS → TESTING → FIXING ↺ → DONE_REPORTED → DONE_VERIFIED → CERTIFIED

Branches :
    IN_PROGRESS → BLOCKED | WAITING_EXTERNAL | DEFERRED

Propriétés :
    - DONE_REPORTED ≠ DONE_VERIFIED (distinction critique — L-055).
    - DONE_VERIFIED ≠ CERTIFIED.
    - Un finding ne disparaît JAMAIS sans transition explicite.
    - CERTIFIED_100 = False invariant absolu.

Corrélation 4 dimensions (ORDRE 4 — R481) :
    SPECIFICATION ↕ CODE ↕ TEST ↕ FORENSIC
    → Un PASS test seul ne certifie jamais.
    → Un finding forensic contradisant un test PASS = anomalie P0.

Persistance : JSON append-only dans logs/anomaly_registry.jsonl
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R484

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.audit.anomaly_registry")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_PATH = _REPO_ROOT / "logs" / "anomaly_registry.jsonl"

# États valides
VALID_STATUSES = {
    "OPEN", "IN_PROGRESS", "TESTING", "FIXING",
    "BLOCKED", "WAITING_EXTERNAL", "DEFERRED",
    "DONE_REPORTED", "DONE_VERIFIED", "CERTIFIED",
    "WONTFIX", "DUPLICATE",
}

# Transitions autorisées
_TRANSITIONS: dict[str, set[str]] = {
    "OPEN":             {"IN_PROGRESS", "WONTFIX", "DUPLICATE"},
    "IN_PROGRESS":      {"TESTING", "BLOCKED", "WAITING_EXTERNAL", "DEFERRED", "DONE_REPORTED"},
    "TESTING":          {"FIXING", "DONE_REPORTED", "IN_PROGRESS"},
    "FIXING":           {"TESTING", "IN_PROGRESS"},
    "BLOCKED":          {"IN_PROGRESS", "WONTFIX"},
    "WAITING_EXTERNAL": {"IN_PROGRESS", "WONTFIX"},
    "DEFERRED":         {"OPEN", "IN_PROGRESS"},
    "DONE_REPORTED":    {"DONE_VERIFIED", "IN_PROGRESS"},
    "DONE_VERIFIED":    {"CERTIFIED", "IN_PROGRESS"},
    "CERTIFIED":        set(),   # état terminal
    "WONTFIX":          set(),
    "DUPLICATE":        set(),
}


# ─── Structures de données ────────────────────────────────────────────────────

@dataclass
class AnomalyEvidence:
    """Preuve rattachée à une anomalie (test, forensic, spec, commit)."""
    evidence_type: str   # "TEST_PASS" | "TEST_FAIL" | "FORENSIC" | "SPEC" | "COMMIT"
    reference: str       # ex: "T07 PASS", "EVT-00042", "CR-087", "aef18b4"
    detail: str = ""
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


@dataclass
class Anomaly:
    """Anomalie canonique ARTCB.

    finding_id   : identifiant stable (ANOMALY-YYYYMMDD-NNNN)
    severity     : CRITICAL | HIGH | MEDIUM | LOW | INFO
    source       : UAP | UPF | TEST | FORENSIC | MANUAL | CALL_GRAPH
    module       : chemin relatif du module concerné
    function     : nom qualifié de la fonction concernée (optionnel)
    spec_ref     : référence à une règle/spec (ex: CR-087, R481 ORDRE 3)
    test_ref     : référence au test (ex: T07)
    forensic_ref : référence à un événement forensic
    status       : état courant (machine d'état)
    root_cause   : cause racine identifiée
    correction   : correction appliquée ou prévue
    commit_sha   : SHA du commit où l'anomalie a été détectée
    evidence     : liste de preuves rattachées
    """
    finding_id: str
    severity: str
    source: str
    message: str
    module: str = ""
    function: str = ""
    spec_ref: str = ""
    test_ref: str = ""
    forensic_ref: str = ""
    status: str = "OPEN"
    root_cause: str = ""
    correction: str = ""
    commit_sha: str = ""
    first_seen_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    last_updated_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    evidence: list[AnomalyEvidence] = field(default_factory=list)
    certified_100: bool = False       # invariant absolu
    unique_human_proven: bool = False  # invariant absolu

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "source": self.source,
            "message": self.message,
            "module": self.module,
            "function": self.function,
            "spec_ref": self.spec_ref,
            "test_ref": self.test_ref,
            "forensic_ref": self.forensic_ref,
            "status": self.status,
            "root_cause": self.root_cause,
            "correction": self.correction,
            "commit_sha": self.commit_sha,
            "first_seen_utc": self.first_seen_utc,
            "last_updated_utc": self.last_updated_utc,
            "evidence": [
                {
                    "evidence_type": e.evidence_type,
                    "reference": e.reference,
                    "detail": e.detail,
                    "timestamp_utc": e.timestamp_utc,
                }
                for e in self.evidence
            ],
            "certified_100": False,
            "unique_human_proven": False,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Anomaly":
        evidence = [
            AnomalyEvidence(
                evidence_type=e.get("evidence_type", ""),
                reference=e.get("reference", ""),
                detail=e.get("detail", ""),
                timestamp_utc=e.get("timestamp_utc", ""),
            )
            for e in d.get("evidence", [])
        ]
        return cls(
            finding_id=d["finding_id"],
            severity=d.get("severity", "INFO"),
            source=d.get("source", "MANUAL"),
            message=d.get("message", ""),
            module=d.get("module", ""),
            function=d.get("function", ""),
            spec_ref=d.get("spec_ref", ""),
            test_ref=d.get("test_ref", ""),
            forensic_ref=d.get("forensic_ref", ""),
            status=d.get("status", "OPEN"),
            root_cause=d.get("root_cause", ""),
            correction=d.get("correction", ""),
            commit_sha=d.get("commit_sha", ""),
            first_seen_utc=d.get("first_seen_utc", ""),
            last_updated_utc=d.get("last_updated_utc", ""),
            evidence=evidence,
        )


# ─── Génération d'ID stable ───────────────────────────────────────────────────

def _generate_finding_id(message: str, module: str, source: str) -> str:
    """Génère un finding_id stable et unique.

    Format : ANOMALY-YYYYMMDD-XXXXXXXX (8 hex de SHA-256 tronqué).
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    payload = f"{source}::{module}::{message}::{time.time_ns()}"
    short_hash = hashlib.sha256(payload.encode()).hexdigest()[:8]
    return f"ANOMALY-{date_str}-{short_hash}"


# ─── Registre ─────────────────────────────────────────────────────────────────

class AnomalyRegistry:
    """Registre canonique des anomalies ARTCB.

    Persistance : JSON Lines append-only dans logs/anomaly_registry.jsonl.
    Chaque mutation (création, transition) est écrite dans le fichier.
    Un finding ne disparaît JAMAIS — seulement les transitions sont ajoutées.
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        self._path = registry_path or _REGISTRY_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._anomalies: dict[str, Anomaly] = {}
        self._load()

    def _load(self) -> None:
        """Charge le registre depuis le fichier JSONL."""
        if not self._path.exists():
            return
        try:
            with self._path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        anomaly = Anomaly.from_dict(d)
                        self._anomalies[anomaly.finding_id] = anomaly
                    except Exception as exc:
                        logger.warning("_load: ligne invalide — %s", exc)
        except Exception as exc:
            logger.warning("AnomalyRegistry._load: erreur — %s", exc)

    def _append(self, anomaly: Anomaly) -> None:
        """Écrit une entrée dans le fichier JSONL (append-only)."""
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(anomaly.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("_append: impossible d'écrire dans le registre — %s", exc)

    def add(
        self,
        severity: str,
        source: str,
        message: str,
        *,
        module: str = "",
        function: str = "",
        spec_ref: str = "",
        test_ref: str = "",
        commit_sha: str = "",
        evidence: list[AnomalyEvidence] | None = None,
    ) -> Anomaly:
        """Ajoute une nouvelle anomalie (status=OPEN).

        Returns:
            L'anomalie créée avec son finding_id stable.
        """
        fid = _generate_finding_id(message, module, source)
        anomaly = Anomaly(
            finding_id=fid,
            severity=severity,
            source=source,
            message=message,
            module=module,
            function=function,
            spec_ref=spec_ref,
            test_ref=test_ref,
            commit_sha=commit_sha,
            evidence=evidence or [],
        )
        self._anomalies[fid] = anomaly
        self._append(anomaly)
        logger.debug("AnomalyRegistry.add: %s %s %s", fid, severity, message[:60])
        return anomaly

    def transition(
        self,
        finding_id: str,
        new_status: str,
        *,
        note: str = "",
        evidence: AnomalyEvidence | None = None,
    ) -> Anomaly:
        """Fait transitionner une anomalie vers un nouvel état.

        Raises:
            KeyError: si finding_id inexistant.
            ValueError: si transition invalide selon la machine d'état.
        """
        if finding_id not in self._anomalies:
            raise KeyError(f"finding_id {finding_id!r} inexistant dans le registre")
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Statut {new_status!r} invalide")

        anomaly = self._anomalies[finding_id]
        allowed = _TRANSITIONS.get(anomaly.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Transition {anomaly.status!r} → {new_status!r} non autorisée. "
                f"Transitions valides depuis {anomaly.status!r} : {allowed}"
            )

        anomaly.status = new_status
        anomaly.last_updated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if note:
            anomaly.root_cause = note if not anomaly.root_cause else anomaly.root_cause
        if evidence:
            anomaly.evidence.append(evidence)
        self._append(anomaly)
        logger.debug("AnomalyRegistry.transition: %s → %s", finding_id, new_status)
        return anomaly

    def get(self, finding_id: str) -> Anomaly | None:
        """Récupère une anomalie par ID."""
        return self._anomalies.get(finding_id)

    def list_open(self) -> list[Anomaly]:
        """Retourne toutes les anomalies non terminées."""
        terminal = {"CERTIFIED", "WONTFIX", "DUPLICATE"}
        return [a for a in self._anomalies.values() if a.status not in terminal]

    def summary(self) -> dict[str, Any]:
        """Résumé du registre."""
        all_anomalies = list(self._anomalies.values())
        by_status: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for a in all_anomalies:
            by_status[a.status] = by_status.get(a.status, 0) + 1
            by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
        return {
            "registry_version": MODULE_VERSION,
            "total": len(all_anomalies),
            "open_count": len(self.list_open()),
            "by_status": by_status,
            "by_severity": by_severity,
            "certified_100": False,
            "unique_human_proven": False,
        }
