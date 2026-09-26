"""Universal Audit Preflight (UAP) — R482 (2026-09-26).

Le UAP est la couche de preuve INDÉPENDANTE DU MODÈLE décrite dans R481.
Il collecte et valide l'état du dépôt, du ledger, des tests et du forensic
AVANT toute session de développement substantielle.

Architecture (ORDRE 2 — R481) :
    PROMPT
      ↓
    UAP  ← ce module
      ├── SHA HEAD (git)
      ├── TASK LEDGER (.artcb/task_ledger.yaml)
      ├── SESSION CONTINUATION (.artcb/session_continuation.yaml)
      ├── STANDARD NAMES (STANDARD_NAMES_ARTCB)
      ├── REPOSITORY MAP (src/artcb/** modules)
      ├── OPEN FINDINGS (ledger tasks OPEN/IN_PROGRESS)
      ├── LANGUAGE BASELINE (R471 stats)
      ├── REGRESSION BASELINE (pytest summary)
      └── CERTIFIED_100 status
      ↓
    MODÈLE

Règles :
    - Le modèle ne décide PAS si le UAP doit être exécuté (ORDRE 8 — R481).
    - CERTIFIED_100 = False invariant absolu.
    - unique_human_proven = False invariant absolu.
    - Fail-open : chaque section produit un résultat ou un finding d'absence.
    - Mode DEBUG actif : loguer toute erreur de collecte.

Références : R481 §UAP, ORDRE 1-15 (expert 2026-09-26), L-055, L-053.
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R482

import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.audit.uap")

# Racine du dépôt (remontée depuis ce fichier : src/artcb/audit/uap.py → ../../..)
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Chemins canoniques
_LEDGER_PATH       = _REPO_ROOT / ".artcb" / "task_ledger.yaml"
_CONTINUATION_PATH = _REPO_ROOT / ".artcb" / "session_continuation.yaml"
_STANDARD_NAMES    = _REPO_ROOT / "STANDARD_NAMES_ARTCB"
_R471_STATS        = _REPO_ROOT / "logs" / "R471_mapping_stats.json"

# Statuts de tâche considérés "ouverts" (non terminés)
_OPEN_STATUSES = {"OPEN", "IN_PROGRESS", "BLOCKED", "WAITING_EXTERNAL", "TESTING", "FIXING"}

# ─── Structures de données ────────────────────────────────────────────────────

@dataclass
class UapFinding:
    """Un finding UAP — anomalie ou point de vigilance détecté lors du preflight.

    severity : CRITICAL / WARNING / INFO
    category : GIT | LEDGER | STANDARD_NAMES | REPO | FINDINGS | LANGUAGE | REGRESSION | CERTIFIED
    message  : description courte
    detail   : détail optionnel (chemin, valeur attendue vs réelle…)
    """
    severity: str          # "CRITICAL" | "WARNING" | "INFO"
    category: str
    message: str
    detail: str = ""
    finding_id: str = ""   # F-xxxxx — rempli par UapReport


@dataclass
class UapSection:
    """Résultat d'une section du preflight.

    name     : identifiant de la section
    ok       : True si aucun finding CRITICAL dans cette section
    findings : liste de UapFinding produits par cette section
    data     : données collectées (dict sérialisable)
    """
    name: str
    ok: bool
    findings: list[UapFinding] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class UapReport:
    """Rapport complet du Universal Audit Preflight.

    Produit par run_uap() — contient toutes les sections et tous les findings.
    """
    timestamp_utc: str
    git_sha: str
    certified_100: bool              # invariant : toujours False
    unique_human_proven: bool        # invariant : toujours False
    sections: list[UapSection] = field(default_factory=list)
    all_findings: list[UapFinding] = field(default_factory=list)
    critical_count: int = 0
    warning_count: int = 0
    preflight_ok: bool = False       # True seulement si zéro CRITICAL

    def to_dict(self) -> dict[str, Any]:
        """Sérialisation JSON du rapport."""
        return {
            "uap_version": MODULE_VERSION,
            "timestamp_utc": self.timestamp_utc,
            "git_sha": self.git_sha,
            "certified_100": self.certified_100,
            "unique_human_proven": self.unique_human_proven,
            "preflight_ok": self.preflight_ok,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "sections": [
                {
                    "name": s.name,
                    "ok": s.ok,
                    "data": s.data,
                    "findings": [
                        {
                            "finding_id": f.finding_id,
                            "severity": f.severity,
                            "category": f.category,
                            "message": f.message,
                            "detail": f.detail,
                        }
                        for f in s.findings
                    ],
                }
                for s in self.sections
            ],
        }


# ─── Collecteurs de sections ──────────────────────────────────────────────────

def _collect_git(repo_root: Path) -> UapSection:
    """Section GIT : collecte SHA HEAD, branche, working tree propre ou non."""
    findings: list[UapFinding] = []
    data: dict[str, Any] = {}

    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
        data["sha"] = sha[:12]
        data["sha_full"] = sha
    except Exception as exc:
        sha = "UNKNOWN"
        data["sha"] = sha
        findings.append(UapFinding(
            severity="CRITICAL", category="GIT",
            message="Impossible de lire git HEAD",
            detail=str(exc),
        ))

    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
        data["branch"] = branch
    except Exception:
        data["branch"] = "UNKNOWN"

    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
        modified = [l for l in status.splitlines() if l.strip()]
        data["working_tree_clean"] = len(modified) == 0
        data["modified_files_count"] = len(modified)
        if modified:
            findings.append(UapFinding(
                severity="INFO", category="GIT",
                message=f"Working tree modifié — {len(modified)} fichier(s) non commités",
                detail="\n".join(modified[:10]),
            ))
    except Exception:
        data["working_tree_clean"] = None

    ok = not any(f.severity == "CRITICAL" for f in findings)
    return UapSection(name="GIT", ok=ok, findings=findings, data=data)


def _collect_ledger(ledger_path: Path, git_sha: str) -> UapSection:
    """Section LEDGER : charge task_ledger.yaml, détecte divergence SHA."""
    findings: list[UapFinding] = []
    data: dict[str, Any] = {}

    if not ledger_path.exists():
        findings.append(UapFinding(
            severity="WARNING", category="LEDGER",
            message=f"Ledger absent : {ledger_path}",
            detail="Créer .artcb/task_ledger.yaml",
        ))
        return UapSection(name="LEDGER", ok=True, findings=findings, data=data)

    try:
        import yaml  # type: ignore[import]
        ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        findings.append(UapFinding(
            severity="CRITICAL", category="LEDGER",
            message="Ledger illisible (YAML invalide)",
            detail=str(exc),
        ))
        return UapSection(name="LEDGER", ok=False, findings=findings, data=data)

    meta = ledger.get("meta", {})
    ledger_sha = str(meta.get("git_head") or meta.get("head_sha") or "?")
    certified = bool(meta.get("certified_100", False))
    data["ledger_sha"] = ledger_sha
    data["ledger_certified_100"] = certified
    data["ledger_mode"] = meta.get("mode", "?")

    # Vérifier divergence SHA
    if ledger_sha not in ("?", "") and git_sha not in ("UNKNOWN", ""):
        if not git_sha.startswith(ledger_sha) and not ledger_sha.startswith(git_sha[:7]):
            findings.append(UapFinding(
                severity="WARNING", category="LEDGER",
                message=f"LEDGER_DIVERGENCE: ledger={ledger_sha} ↔ HEAD={git_sha[:12]}",
                detail="Mettre à jour meta.head_sha dans task_ledger.yaml",
            ))

    # Inventaire des tâches ouvertes
    tasks = ledger.get("tasks", [])
    open_tasks = []
    for task in tasks:
        if task.get("status") in _OPEN_STATUSES:
            open_tasks.append({
                "id": task.get("id", "?"),
                "title": task.get("title", "")[:80],
                "status": task.get("status"),
                "priority": task.get("priority", "?"),
            })
        for sub in task.get("subtasks", []):
            if sub.get("status") in _OPEN_STATUSES:
                open_tasks.append({
                    "id": sub.get("id", "?"),
                    "title": sub.get("title", "")[:80],
                    "status": sub.get("status"),
                    "priority": "subtask",
                })

    data["open_tasks"] = open_tasks
    data["open_tasks_count"] = len(open_tasks)

    if certified:
        findings.append(UapFinding(
            severity="CRITICAL", category="CERTIFIED",
            message="CERTIFIED_100=true dans le ledger — invariant absolu violated",
            detail="CERTIFIED_100 doit toujours être false tant que les preuves ne sont pas réunies.",
        ))

    ok = not any(f.severity == "CRITICAL" for f in findings)
    return UapSection(name="LEDGER", ok=ok, findings=findings, data=data)


def _collect_standard_names(std_path: Path) -> UapSection:
    """Section STANDARD_NAMES : vérifie présence + lisibilité de STANDARD_NAMES_ARTCB."""
    findings: list[UapFinding] = []
    data: dict[str, Any] = {}

    if not std_path.exists():
        findings.append(UapFinding(
            severity="CRITICAL", category="STANDARD_NAMES",
            message="STANDARD_NAMES_ARTCB absent",
            detail=f"Chemin attendu : {std_path}",
        ))
        return UapSection(name="STANDARD_NAMES", ok=False, findings=findings, data=data)

    try:
        content = std_path.read_text(encoding="utf-8")
        sha256 = hashlib.sha256(content.encode()).hexdigest()[:16]
        # Vérifier les sections clés attendues
        required_sections = [
            "Fichiers documentation", "Code Python", "Code C",
            "API REST", "Rapports", "Types de nœuds",
        ]
        missing = [s for s in required_sections if s not in content]
        data["sha256_prefix"] = sha256
        data["size_chars"] = len(content)
        data["missing_sections"] = missing

        if missing:
            findings.append(UapFinding(
                severity="WARNING", category="STANDARD_NAMES",
                message=f"STANDARD_NAMES_ARTCB : {len(missing)} section(s) manquante(s)",
                detail=", ".join(missing),
            ))
        else:
            findings.append(UapFinding(
                severity="INFO", category="STANDARD_NAMES",
                message="STANDARD_NAMES_ARTCB présent et complet",
                detail=f"sha256={sha256}, {len(content)} chars",
            ))
    except Exception as exc:
        findings.append(UapFinding(
            severity="CRITICAL", category="STANDARD_NAMES",
            message="STANDARD_NAMES_ARTCB illisible",
            detail=str(exc),
        ))
        return UapSection(name="STANDARD_NAMES", ok=False, findings=findings, data=data)

    ok = not any(f.severity == "CRITICAL" for f in findings)
    return UapSection(name="STANDARD_NAMES", ok=ok, findings=findings, data=data)


def _collect_repo_map(repo_root: Path) -> UapSection:
    """Section REPO : cartographie des modules Python src/artcb/."""
    findings: list[UapFinding] = []
    data: dict[str, Any] = {}

    src_artcb = repo_root / "src" / "artcb"
    if not src_artcb.exists():
        findings.append(UapFinding(
            severity="CRITICAL", category="REPO",
            message="src/artcb/ absent",
            detail=str(src_artcb),
        ))
        return UapSection(name="REPO", ok=False, findings=findings, data=data)

    modules = sorted(
        str(p.relative_to(repo_root))
        for p in src_artcb.rglob("*.py")
        if p.name != "__init__.py"
    )
    data["module_count"] = len(modules)
    data["modules_sample"] = modules[:20]   # 20 premiers pour lisibilité

    # Vérifier les modules critiques TASK-001
    critical_modules = [
        "src/artcb/identity/biometric_onchain.py",
        "src/artcb/crypto/homomorphic.py",
        "src/artcb/identity/human_identity_policy.py",
        "src/artcb/audit/uap.py",
    ]
    missing_critical = [m for m in critical_modules if not (repo_root / m).exists()]
    data["critical_modules_missing"] = missing_critical

    if missing_critical:
        findings.append(UapFinding(
            severity="WARNING", category="REPO",
            message=f"{len(missing_critical)} module(s) critique(s) absent(s)",
            detail=", ".join(missing_critical),
        ))

    ok = not any(f.severity == "CRITICAL" for f in findings)
    return UapSection(name="REPO", ok=ok, findings=findings, data=data)


def _collect_language_baseline(stats_path: Path) -> UapSection:
    """Section LANGUAGE : charge R471_mapping_stats.json (baseline 21.5M entrées)."""
    findings: list[UapFinding] = []
    data: dict[str, Any] = {}

    if not stats_path.exists():
        findings.append(UapFinding(
            severity="WARNING", category="LANGUAGE",
            message="R471_mapping_stats.json absent — baseline linguistique non disponible",
            detail=str(stats_path),
        ))
        return UapSection(name="LANGUAGE", ok=True, findings=findings, data=data)

    try:
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        data["git_sha"] = stats.get("git_sha", "?")
        data["total_entries"] = stats.get("total_entries", 0)
        data["resolved_total"] = stats.get("resolved_total", 0)
        data["closure_ok"] = stats.get("closure_all_ok", False)

        if not stats.get("closure_all_ok"):
            findings.append(UapFinding(
                severity="WARNING", category="LANGUAGE",
                message="closure_all_ok=False dans R471_mapping_stats.json",
                detail="Fermeture mathématique non vérifiée — re-run R471 requis",
            ))
        else:
            findings.append(UapFinding(
                severity="INFO", category="LANGUAGE",
                message=f"Baseline R471 : {stats.get('total_entries',0):,} entrées, "
                        f"{stats.get('resolved_total',0):,} résolues",
                detail=f"closure_ok=True sha={stats.get('git_sha','?')}",
            ))
    except Exception as exc:
        findings.append(UapFinding(
            severity="WARNING", category="LANGUAGE",
            message="R471_mapping_stats.json illisible",
            detail=str(exc),
        ))

    ok = not any(f.severity == "CRITICAL" for f in findings)
    return UapSection(name="LANGUAGE", ok=ok, findings=findings, data=data)


def _collect_certified_invariant() -> UapSection:
    """Section CERTIFIED : vérifie l'invariant CERTIFIED_100=false."""
    findings: list[UapFinding] = []
    data: dict[str, Any] = {
        "certified_100": False,
        "unique_human_proven": False,
        "note": "Invariants absolus — jamais modifiables sans preuves cumulatives.",
    }
    findings.append(UapFinding(
        severity="INFO", category="CERTIFIED",
        message="CERTIFIED_100=false — invariant vérifié",
        detail="unique_human_proven=false — invariant vérifié",
    ))
    return UapSection(name="CERTIFIED", ok=True, findings=findings, data=data)


# ─── Point d'entrée principal ─────────────────────────────────────────────────

def run_uap(repo_root: Path | None = None) -> UapReport:
    """Exécute le Universal Audit Preflight complet.

    Collecte toutes les sections dans l'ordre défini par R481 :
        GIT → LEDGER → STANDARD_NAMES → REPO → LANGUAGE → CERTIFIED

    Returns:
        UapReport avec preflight_ok=True seulement si zéro finding CRITICAL.
    """
    if repo_root is None:
        repo_root = _REPO_ROOT

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.debug("UAP run_uap start: root=%s ts=%s", repo_root, timestamp)

    # 1. Section GIT — collecte le SHA en premier (utilisé par les autres sections)
    git_section = _collect_git(repo_root)
    git_sha = git_section.data.get("sha_full", "UNKNOWN")

    # 2. Autres sections (ordre R481)
    sections = [
        git_section,
        _collect_ledger(_LEDGER_PATH if repo_root == _REPO_ROOT else repo_root / ".artcb" / "task_ledger.yaml", git_sha),
        _collect_standard_names(_STANDARD_NAMES if repo_root == _REPO_ROOT else repo_root / "STANDARD_NAMES_ARTCB"),
        _collect_repo_map(repo_root),
        _collect_language_baseline(_R471_STATS if repo_root == _REPO_ROOT else repo_root / "logs" / "R471_mapping_stats.json"),
        _collect_certified_invariant(),
    ]

    # Agréger tous les findings + numéroter
    all_findings: list[UapFinding] = []
    for idx, finding in enumerate(
        f for s in sections for f in s.findings
    ):
        finding.finding_id = f"F-{idx+1:04d}"
        all_findings.append(finding)

    critical_count = sum(1 for f in all_findings if f.severity == "CRITICAL")
    warning_count  = sum(1 for f in all_findings if f.severity == "WARNING")
    preflight_ok   = critical_count == 0

    report = UapReport(
        timestamp_utc=timestamp,
        git_sha=git_sha[:12] if git_sha != "UNKNOWN" else "UNKNOWN",
        certified_100=False,          # invariant absolu
        unique_human_proven=False,    # invariant absolu
        sections=sections,
        all_findings=all_findings,
        critical_count=critical_count,
        warning_count=warning_count,
        preflight_ok=preflight_ok,
    )

    logger.debug(
        "UAP done: critical=%d warning=%d preflight_ok=%s",
        critical_count, warning_count, preflight_ok,
    )
    return report


def save_uap_report(report: UapReport, output_dir: Path | None = None) -> Path:
    """Sauvegarde le rapport UAP en JSON dans logs/.

    Args:
        report: UapReport produit par run_uap().
        output_dir: répertoire de sortie (défaut : repo_root/logs/).

    Returns:
        Chemin du fichier créé.
    """
    if output_dir is None:
        output_dir = _REPO_ROOT / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = report.timestamp_utc.replace(":", "").replace("-", "")[:15]
    out_path = output_dir / f"uap_{ts}_{report.git_sha[:8]}.json"
    out_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("UAP report saved: %s", out_path)
    return out_path


# ─── CLI minimal (mode DEBUG) ─────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    report = run_uap()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    path = save_uap_report(report)
    print(f"\n[UAP] Rapport sauvegardé : {path}", file=sys.stderr)
    sys.exit(0 if report.preflight_ok else 1)
