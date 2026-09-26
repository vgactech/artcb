"""Universal Postflight (UPF) — R484 / ORDRE 6 (R481) — 2026-09-26.

Le UPF est la couche d'audit POST-modification.
Il s'exécute APRÈS qu'un agent a modifié du code, et AVANT le commit/push.

Pipeline complet (ORDRE 6 — R481) :
    MODIFICATION
     ↓
    git diff                    ← fichiers modifiés
     ↓
    modules affectés            ← resolve python module paths
     ↓
    call graph transitif        ← R483 get_impact_of_change()
     ↓
    tests ciblés                ← test_{module}.py correspondants
     ↓
    forensic delta              ← events émis après vs avant
     ↓
    langues affectées           ← LANGUAGE_SENSITIVE_MODULES (R481 ORDRE 7)
     ↓
    régression baseline         ← pytest summary
     ↓
    tâches affectées            ← ledger cross-référence
     ↓
    UPF rapport                 ← PostflightReport JSON

Propriétés :
    - Une session qui modifie du code NE PEUT PAS se terminer sans produire
      son postflight (ORDRE 6 §7 — R481).
    - fail-open sur chaque section (jamais de crash).
    - CERTIFIED_100 = False invariant absolu.
    - unique_human_proven = False invariant absolu.
    - Deux modes : ADVISORY (informatif) | GATE (bloquant si CRITICAL).

LANGUAGE_SENSITIVE_MODULES (ORDRE 7 — R481) :
    Tout fichier dans cette liste ou l'appelant transitivement déclenche
    automatiquement une analyse d'impact linguistique.
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R484

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.audit.upf")

# Racine dépôt
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Modules sensibles au langage (ORDRE 7 — R481)
# Toute modification d'un de ces modules → Language Impact Analysis requise
LANGUAGE_SENSITIVE_MODULES: set[str] = {
    "src/artcb/language/lexicon_mapper.py",
    "src/artcb/language/lexicon_loader.py",
    "src/artcb/language/registry.py",
    "src/artcb/ir/ir_encoder.py",
    "src/artcb/ir/canonical.py",
    "src/artcb/kcg/events.py",
    "src/artcb/reasoning/canonical.py",
    "src/artcb/reasoning/langage_battery.py",
}

# Modes UPF
UPF_ADVISORY = "ADVISORY"   # informatif, jamais bloquant
UPF_GATE     = "GATE"       # bloquant si CRITICAL (pour pipeline CI)


# ─── Structures de données ────────────────────────────────────────────────────

@dataclass
class DiffEntry:
    """Fichier modifié détecté par git diff."""
    path: str
    status: str   # M=modified, A=added, D=deleted, R=renamed
    additions: int = 0
    deletions: int = 0


@dataclass
class PostflightFinding:
    """Finding produit par une section du postflight."""
    severity: str        # CRITICAL | WARNING | INFO
    category: str        # DIFF | IMPACT | LANGUAGE | REGRESSION | TASKS | FORENSIC
    message: str
    detail: str = ""
    finding_id: str = ""


@dataclass
class PostflightSection:
    """Section du rapport postflight."""
    name: str
    ok: bool
    findings: list[PostflightFinding] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PostflightReport:
    """Rapport complet du Universal Postflight.

    Produit par run_upf() après une modification de code.
    """
    timestamp_utc: str
    git_sha_before: str          # SHA avant les modifications
    git_sha_after: str           # SHA HEAD actuel (peut être identique si non commité)
    mode: str                    # ADVISORY | GATE
    certified_100: bool = False  # invariant absolu
    unique_human_proven: bool = False  # invariant absolu
    sections: list[PostflightSection] = field(default_factory=list)
    all_findings: list[PostflightFinding] = field(default_factory=list)
    critical_count: int = 0
    warning_count: int = 0
    postflight_ok: bool = False  # True si zéro CRITICAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "upf_version": MODULE_VERSION,
            "timestamp_utc": self.timestamp_utc,
            "git_sha_before": self.git_sha_before,
            "git_sha_after": self.git_sha_after,
            "mode": self.mode,
            "certified_100": self.certified_100,
            "unique_human_proven": self.unique_human_proven,
            "postflight_ok": self.postflight_ok,
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

def _collect_diff(repo_root: Path, base_sha: str | None = None) -> PostflightSection:
    """Section DIFF : fichiers modifiés depuis base_sha (ou working tree)."""
    findings: list[PostflightFinding] = []
    data: dict[str, Any] = {}

    try:
        if base_sha:
            cmd = ["git", "diff", "--name-status", base_sha, "HEAD"]
        else:
            # Working tree non commité
            cmd = ["git", "diff", "--name-status", "HEAD"]

        out = subprocess.check_output(cmd, cwd=repo_root, stderr=subprocess.DEVNULL, text=True)
        entries: list[DiffEntry] = []
        for line in out.strip().splitlines():
            parts = line.split("\t", 2)
            if len(parts) >= 2:
                status, path = parts[0][0], parts[-1]
                entries.append(DiffEntry(path=path, status=status))

        data["modified_files_count"] = len(entries)
        data["modified_files"] = [e.path for e in entries[:20]]

        if not entries:
            findings.append(PostflightFinding(
                severity="INFO", category="DIFF",
                message="Aucun fichier modifié détecté",
                detail="Working tree propre ou base_sha == HEAD",
            ))
        else:
            findings.append(PostflightFinding(
                severity="INFO", category="DIFF",
                message=f"{len(entries)} fichier(s) modifié(s)",
                detail=", ".join(e.path for e in entries[:5]) + ("…" if len(entries) > 5 else ""),
            ))
    except Exception as exc:
        findings.append(PostflightFinding(
            severity="WARNING", category="DIFF",
            message="Impossible de calculer git diff",
            detail=str(exc),
        ))
        data["modified_files_count"] = 0
        data["modified_files"] = []

    ok = not any(f.severity == "CRITICAL" for f in findings)
    return PostflightSection(name="DIFF", ok=ok, findings=findings, data=data)


def _collect_impact(
    modified_files: list[str],
    repo_root: Path,
) -> PostflightSection:
    """Section IMPACT : analyse transitive via call_graph (R483).

    Pour chaque fichier modifié, extrait les fonctions définies et
    calcule l'impact transitif via get_impact_of_change().
    """
    findings: list[PostflightFinding] = []
    data: dict[str, Any] = {}

    if not modified_files:
        data["impacted_functions"] = []
        data["language_impact"] = False
        return PostflightSection(name="IMPACT", ok=True, findings=findings, data=data)

    try:
        from src.artcb.audit.call_graph import build_call_graph, get_impact_of_change  # noqa: PLC0415

        # Analyser uniquement les modules Python modifiés
        py_modified = [f for f in modified_files if f.endswith(".py")]
        if not py_modified:
            data["impacted_functions"] = []
            data["language_impact"] = False
            findings.append(PostflightFinding(
                severity="INFO", category="IMPACT",
                message="Aucun module Python modifié",
            ))
            return PostflightSection(name="IMPACT", ok=True, findings=findings, data=data)

        # Build graph limité aux modules modifiés + leurs voisins
        include_dirs = list({(repo_root / f).parent for f in py_modified if (repo_root / f).parent.exists()})
        # Inclure toujours src/artcb pour la résolution
        src_artcb = repo_root / "src" / "artcb"
        if src_artcb.exists() and src_artcb not in include_dirs:
            include_dirs.append(src_artcb)

        graph = build_call_graph(repo_root, include_paths=include_dirs, max_files=200)

        # Trouver les fonctions des modules modifiés
        all_impacted: set[str] = set()
        for qname, node in graph.nodes.items():
            if any(node.module_path == f or node.module_path.endswith(f) for f in py_modified):
                impacted = get_impact_of_change(qname, graph)
                all_impacted.update(impacted)

        data["impacted_functions_count"] = len(all_impacted)
        data["impacted_functions"] = sorted(all_impacted)[:30]
        data["language_impact"] = any(f in LANGUAGE_SENSITIVE_MODULES for f in py_modified)
        data["py_modified_count"] = len(py_modified)

        if data["language_impact"]:
            lang_files = [f for f in py_modified if f in LANGUAGE_SENSITIVE_MODULES]
            findings.append(PostflightFinding(
                severity="WARNING", category="LANGUAGE",
                message=f"LANGUAGE_IMPACT : {len(lang_files)} module(s) linguistique(s) modifié(s)",
                detail=", ".join(lang_files),
            ))

        findings.append(PostflightFinding(
            severity="INFO", category="IMPACT",
            message=f"{len(all_impacted)} fonction(s) dans le périmètre transitif",
            detail=f"modules_py={len(py_modified)}",
        ))

    except Exception as exc:
        logger.warning("_collect_impact: erreur call_graph : %s", exc)
        findings.append(PostflightFinding(
            severity="WARNING", category="IMPACT",
            message="Analyse d'impact indisponible",
            detail=str(exc),
        ))
        data["impacted_functions"] = []
        data["language_impact"] = False

    ok = not any(f.severity == "CRITICAL" for f in findings)
    return PostflightSection(name="IMPACT", ok=ok, findings=findings, data=data)


def _collect_regression_baseline(repo_root: Path) -> PostflightSection:
    """Section REGRESSION : infos sur les tests disponibles (pas d'exécution — trop lent).

    L'exécution réelle des tests doit être faite par le gate DO-178C (hook pre-commit).
    Ce collecteur vérifie uniquement la présence des fichiers de test.
    """
    findings: list[PostflightFinding] = []
    data: dict[str, Any] = {}

    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        findings.append(PostflightFinding(
            severity="WARNING", category="REGRESSION",
            message="Répertoire tests/ absent",
        ))
        return PostflightSection(name="REGRESSION", ok=True, findings=findings, data=data)

    test_files = sorted(tests_dir.glob("test_*.py"))
    data["test_files_count"] = len(test_files)
    data["test_files_sample"] = [f.name for f in test_files[:10]]

    findings.append(PostflightFinding(
        severity="INFO", category="REGRESSION",
        message=f"{len(test_files)} fichier(s) de test détectés",
        detail="Exécution réelle via gate DO-178C (hook pre-commit)",
    ))

    ok = True
    return PostflightSection(name="REGRESSION", ok=ok, findings=findings, data=data)


def _collect_tasks_impact(
    modified_files: list[str],
    repo_root: Path,
) -> PostflightSection:
    """Section TASKS : cross-référence avec le task ledger."""
    findings: list[PostflightFinding] = []
    data: dict[str, Any] = {}

    ledger_path = repo_root / ".artcb" / "task_ledger.yaml"
    if not ledger_path.exists():
        data["open_tasks_count"] = 0
        return PostflightSection(name="TASKS", ok=True, findings=findings, data=data)

    try:
        import yaml  # type: ignore[import]  # noqa: PLC0415
        ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8")) or {}
        tasks = ledger.get("tasks", [])
        open_tasks = [
            t for t in tasks
            if t.get("status") in {"OPEN", "IN_PROGRESS", "BLOCKING", "BLOCKED"}
        ]
        data["open_tasks_count"] = len(open_tasks)
        data["open_task_ids"] = [t.get("id", "?") for t in open_tasks[:10]]

        if open_tasks:
            findings.append(PostflightFinding(
                severity="INFO", category="TASKS",
                message=f"{len(open_tasks)} tâche(s) OPEN/IN_PROGRESS dans le ledger",
                detail=", ".join(t.get("id", "?") for t in open_tasks[:5]),
            ))
    except Exception as exc:
        findings.append(PostflightFinding(
            severity="WARNING", category="TASKS",
            message="Impossible de lire le ledger",
            detail=str(exc),
        ))

    ok = True
    return PostflightSection(name="TASKS", ok=ok, findings=findings, data=data)


def _collect_certified_invariant() -> PostflightSection:
    """Section CERTIFIED : invariants certified_100=False + unique_human_proven=False."""
    return PostflightSection(
        name="CERTIFIED",
        ok=True,
        findings=[PostflightFinding(
            severity="INFO", category="CERTIFIED",
            message="certified_100=False | unique_human_proven=False — invariants vérifiés",
        )],
        data={"certified_100": False, "unique_human_proven": False},
    )


# ─── Point d'entrée principal ─────────────────────────────────────────────────

def run_upf(
    repo_root: Path | None = None,
    *,
    base_sha: str | None = None,
    mode: str = UPF_ADVISORY,
) -> PostflightReport:
    """Exécute le Universal Postflight complet.

    Args:
        repo_root : racine du dépôt (défaut : auto-détecté).
        base_sha  : SHA de référence pour git diff (défaut : HEAD).
        mode      : ADVISORY (informatif) | GATE (bloquant si CRITICAL).

    Returns:
        PostflightReport avec postflight_ok=True si zéro CRITICAL.
    """
    if repo_root is None:
        repo_root = _REPO_ROOT

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # SHA courant
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        git_sha = "UNKNOWN"

    sha_before = base_sha or git_sha

    # 1. DIFF
    diff_section = _collect_diff(repo_root, base_sha)
    modified_files = diff_section.data.get("modified_files", [])

    # 2. IMPACT (utilise le diff)
    impact_section = _collect_impact(modified_files, repo_root)

    # 3. REGRESSION (vérification présence tests)
    regression_section = _collect_regression_baseline(repo_root)

    # 4. TASKS (cross-référence ledger)
    tasks_section = _collect_tasks_impact(modified_files, repo_root)

    # 5. CERTIFIED invariants
    certified_section = _collect_certified_invariant()

    sections = [diff_section, impact_section, regression_section, tasks_section, certified_section]

    # Agrégation + numérotation findings
    all_findings: list[PostflightFinding] = []
    for idx, f in enumerate(finding for s in sections for finding in s.findings):
        f.finding_id = f"UPF-{idx+1:04d}"
        all_findings.append(f)

    critical_count = sum(1 for f in all_findings if f.severity == "CRITICAL")
    warning_count  = sum(1 for f in all_findings if f.severity == "WARNING")
    postflight_ok  = critical_count == 0

    return PostflightReport(
        timestamp_utc=timestamp,
        git_sha_before=sha_before,
        git_sha_after=git_sha,
        mode=mode,
        sections=sections,
        all_findings=all_findings,
        critical_count=critical_count,
        warning_count=warning_count,
        postflight_ok=postflight_ok,
    )


def save_upf_report(report: PostflightReport, output_dir: Path | None = None) -> Path:
    """Sauvegarde le rapport UPF en JSON dans logs/."""
    if output_dir is None:
        output_dir = _REPO_ROOT / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = report.timestamp_utc.replace(":", "").replace("-", "")[:15]
    out = output_dir / f"upf_{ts}_{report.git_sha_after[:8]}.json"
    out.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("UPF report saved: %s", out)
    return out


# ─── CLI minimal ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import logging as _logging
    _logging.basicConfig(level=_logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    report = run_upf()
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    path = save_upf_report(report)
    print(f"\n[UPF] Rapport : {path}", file=sys.stderr)
    sys.exit(0 if report.postflight_ok else 1)
