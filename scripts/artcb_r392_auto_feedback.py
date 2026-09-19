#!/usr/bin/env python3
"""
R392 v2 — Auto-feedback post-tâche ARTCB basé sur FAITS mesurés.

R394-C : branchement stop.py prouvé (instructions d'intégration dans main())
R394-D : analyse basée sur faits réels (tests PASS/FAIL/régression, fichiers modifiés,
         couverture MODULE_VERSION, CERTIFIED_100) — plus de mots-clés de commit.

Mécanisme :
  - Lit les résultats pytest depuis un fichier JSON (--test-results)
  - Lit git log, git diff --stat
  - Lit le fingerprint R394-B (logs/R394_module_fingerprints.json)
  - Produit un rapport RETRO_<date>_<sha>.md avec :
      FAITS : tests PASS/FAIL, fichiers touchés, couverture versioning
      OBSERVATIONS : régressions, nouveaux tests, modules sans version
      RISQUES : CERTIFIED_100=false, tests en échec, modules non versionnés
      LEÇONS : déclenchées si des patterns connus sont détectés
      ACTIONS : tâches suivantes à documenter

Usage:
    python3 scripts/artcb_r392_auto_feedback.py [--since <sha>] [--test-results <json>]
    python3 scripts/artcb_r392_auto_feedback.py --since HEAD~5

Intégration stop.py (R394-C) :
    Ajouter dans .bob/hooks/stop.py :
        import subprocess, os
        repo = os.environ.get("ARTCB_REPO_PATH", os.getcwd())
        subprocess.run(
            ["python3", "scripts/artcb_r392_auto_feedback.py", "--since", "HEAD~1"],
            cwd=repo, timeout=30
        )

CERTIFIED_100=false | DEBUG MODE
"""

from __future__ import annotations

MODULE_VERSION = '1.1.0'  # R394-D — feedback basé sur faits

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: list[str], *, timeout: int = 15) -> str:
    """Exécute une commande, retourne stdout ou '' si erreur."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(REPO_ROOT))
        return r.stdout.strip()
    except Exception:
        return ""


def _relative(path: str) -> str:
    """Normalise un chemin en relatif sans /Users/xxx."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return path


# ── Collecte faits git ────────────────────────────────────────────────────────

def collect_git_facts(since_sha: str | None) -> dict:
    """Retourne les faits git bruts : commits, fichiers modifiés, insertions/suppressions."""
    current_sha = _run(["git", "rev-parse", "--short", "HEAD"]) or "unknown"

    ref = f"{since_sha}..HEAD" if since_sha else "-5"
    log_out = _run(["git", "log", ref if ".." in str(ref) else f"-{ref.lstrip('-')}",
                    "--oneline"])
    commits = []
    for line in log_out.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commits.append({"sha": parts[0], "msg": parts[1]})

    diff_ref = f"{since_sha}..HEAD" if since_sha else "HEAD~1..HEAD"
    diff_out = _run(["git", "diff", "--stat", diff_ref])
    diff_lines = diff_out.splitlines()
    diff_summary = diff_lines[-1].strip() if diff_lines else ""
    files_changed = []
    insertions = 0
    deletions = 0
    for line in diff_lines:
        if "|" in line:
            fn = _relative(line.split("|")[0].strip())
            files_changed.append(fn)
        # Extraire insertions/suppressions de la ligne résumé
        m = re.search(r"(\d+) insertion", diff_summary)
        if m:
            insertions = int(m.group(1))
        m = re.search(r"(\d+) deletion", diff_summary)
        if m:
            deletions = int(m.group(1))

    return {
        "current_sha": current_sha,
        "since_sha": since_sha,
        "commits": commits,
        "commits_count": len(commits),
        "files_changed": files_changed,
        "files_changed_count": len(files_changed),
        "insertions": insertions,
        "deletions": deletions,
        "diff_summary": diff_summary,
    }


# ── Collecte faits tests ──────────────────────────────────────────────────────

def collect_test_facts(test_results_path: str | None) -> dict:
    """Lit un fichier JSON pytest ou cherche dans les logs récents.

    Format attendu du JSON pytest :
      {"passed": 99, "failed": 0, "errors": 0, "warnings": 3,
       "test_ids_failed": ["tests/test_x.py::test_y"], "duration_s": 6.8}

    Si introuvable : retourne {"status": "not_measured"}.
    """
    # 1. Fichier explicite
    if test_results_path and Path(test_results_path).exists():
        with open(test_results_path) as f:
            data = json.load(f)
        data["source"] = _relative(test_results_path)
        return data

    # 2. Cherche dans logs/ un fichier pytest récent (.txt)
    log_dir = REPO_ROOT / "logs"
    if log_dir.exists():
        candidates = sorted(log_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        for c in candidates[:5]:
            content = c.read_text(errors="ignore")
            m_pass = re.search(r"(\d+) passed", content)
            m_fail = re.search(r"(\d+) failed", content)
            m_err = re.search(r"(\d+) error", content)
            if m_pass:
                passed = int(m_pass.group(1))
                failed = int(m_fail.group(1)) if m_fail else 0
                errors = int(m_err.group(1)) if m_err else 0
                # Lire les IDs de tests en échec depuis le fichier
                failed_ids = re.findall(r"FAILED (tests/[^\s]+)", content)
                return {
                    "source": _relative(str(c)),
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "test_ids_failed": failed_ids[:20],
                    "status": "from_log",
                }
    return {"status": "not_measured"}


# ── Collecte faits versioning ─────────────────────────────────────────────────

def collect_versioning_facts() -> dict:
    """Lit logs/R394_module_fingerprints.json si présent."""
    fp_path = REPO_ROOT / "logs" / "R394_module_fingerprints.json"
    if fp_path.exists():
        with open(fp_path) as f:
            data = json.load(f)
        total = data.get("total", 0)
        with_version = data.get("with_version", 0)
        without = [m["path"] for m in data.get("modules", [])
                   if not m.get("has_module_version", True)]
        return {
            "source": "logs/R394_module_fingerprints.json",
            "total": total,
            "with_version": with_version,
            "without_version": len(without),
            "coverage_pct": round(100 * with_version / max(total, 1), 1),
            "missing_sample": without[:5],
        }
    # Fallback : compter directement
    total = 0
    versioned = 0
    missing = []
    src = REPO_ROOT / "src"
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if "__pycache__" not in d]
        for fn in files:
            if fn.endswith(".py") and fn != "__init__.py":
                total += 1
                content = (Path(root) / fn).read_text(errors="ignore")
                if "MODULE_VERSION" in content:
                    versioned += 1
                else:
                    missing.append(_relative(str(Path(root) / fn)))
    return {
        "source": "direct_scan",
        "total": total,
        "with_version": versioned,
        "without_version": len(missing),
        "coverage_pct": round(100 * versioned / max(total, 1), 1),
        "missing_sample": missing[:5],
    }


# ── Analyse des faits → FAITS/OBSERVATIONS/RISQUES/LEÇONS/ACTIONS ────────────

def analyze(git: dict, tests: dict, versioning: dict) -> dict:
    """Analyse basée sur les faits mesurés — aucun mot-clé de commit."""

    facts = []
    observations = []
    risks = []
    lessons = []
    actions = []

    # ── FAITS ──────────────────────────────────────────────────────────────
    facts.append(f"SHA actuel : {git['current_sha']}")
    facts.append(f"Commits depuis {git['since_sha'] or 'début'} : {git['commits_count']}")
    facts.append(f"Fichiers modifiés : {git['files_changed_count']} ({git['diff_summary']})")

    if tests.get("status") == "not_measured":
        facts.append("Tests : non mesurés dans cette session")
    else:
        passed = tests.get("passed", 0)
        failed = tests.get("failed", 0)
        errors = tests.get("errors", 0)
        facts.append(f"Tests : {passed} PASS / {failed} FAIL / {errors} ERROR")

    facts.append(
        f"Versioning : {versioning['with_version']}/{versioning['total']} modules "
        f"({versioning['coverage_pct']}%)"
    )
    facts.append("CERTIFIED_100=false (invariant — ne jamais inventer)")

    # ── OBSERVATIONS ───────────────────────────────────────────────────────
    if tests.get("failed", 0) > 0:
        failed_ids = tests.get("test_ids_failed", [])
        observations.append(f"{tests['failed']} test(s) en ÉCHEC détectés :")
        for tid in failed_ids[:5]:
            observations.append(f"  - {tid}")
        if len(failed_ids) > 5:
            observations.append(f"  - ... ({len(failed_ids) - 5} autres)")

    if versioning["without_version"] > 0:
        observations.append(
            f"{versioning['without_version']} module(s) sans MODULE_VERSION détectés "
            f"(R390 à relancer)"
        )
        for p in versioning["missing_sample"]:
            observations.append(f"  - {p}")

    if git["insertions"] > 500:
        observations.append(
            f"Session à fort volume : +{git['insertions']} insertions. "
            f"Vérifier les tests de non-régression."
        )

    # Fichiers src modifiés
    src_files = [f for f in git["files_changed"] if f.startswith("src/")]
    if src_files:
        observations.append(f"Modules src modifiés dans cette session ({len(src_files)}) :")
        for fn in src_files[:8]:
            observations.append(f"  - {fn}")

    # ── RISQUES ────────────────────────────────────────────────────────────
    risks.append("CERTIFIED_100=false — tout bloc mainnet doit être retesté live avant certif")

    if tests.get("failed", 0) > 0:
        risks.append(f"TESTS EN ÉCHEC ({tests['failed']}) — ne pas merger ni déployer avant résolution")

    if tests.get("status") == "not_measured":
        risks.append("Tests non mesurés dans cette session — lancer pytest avant push")

    if versioning["without_version"] > 0:
        risks.append(
            f"Modules sans versioning : traçabilité incomplète "
            f"({versioning['without_version']} modules)"
        )

    # ── LEÇONS (déclenchées sur faits, pas mots-clés) ─────────────────────
    if any("requirements.txt" in f for f in git["files_changed"]):
        lessons.append(
            "L-048 : requirements.txt modifié → faire pip install sur tous les nœuds live "
            "AVANT de redémarrer le service."
        )

    if git["commits_count"] == 0:
        lessons.append(
            "L-049 : Working tree modifié mais aucun commit détecté. "
            "Vérifier git status avant de marquer une tâche DONE."
        )

    if git["files_changed_count"] > 30:
        lessons.append(
            "Session très large (>30 fichiers). "
            "Préférer des commits atomiques par fonctionnalité."
        )

    # ── ACTIONS ────────────────────────────────────────────────────────────
    if tests.get("failed", 0) > 0:
        actions.append("Corriger les tests en échec avant le prochain push")

    actions.append("Déployer R387+R390 sur N2/N4/N3 (TASK-006-LIVE-VALIDATION)")
    actions.append("FHE check_uniqueness() — capteurs réels FAR/FRR (TASK-001-BIOMETRIE-SUITE)")
    actions.append(
        "Intégrer R392 dans .bob/hooks/stop.py pour déclenchement automatique (R394-C)"
    )

    return {
        "facts": facts,
        "observations": observations,
        "risks": risks,
        "lessons": lessons,
        "actions": actions,
    }


# ── Génération rapport Markdown ───────────────────────────────────────────────

def generate_report(since_sha: str | None, test_results_path: str | None,
                    repo: Path) -> Path:
    ts = datetime.now(timezone.utc)
    git = collect_git_facts(since_sha)
    tests = collect_test_facts(test_results_path)
    versioning = collect_versioning_facts()
    analysis = analyze(git, tests, versioning)

    lines = [
        f"# Rétrospective ARTCB — {ts.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        f"> **SHA** : `{git['current_sha']}` | **Référence** : `{since_sha or 'last 5 commits'}`",
        f"> `CERTIFIED_100=false` | Mode DEBUG | R392 v1.1 (R394-D)",
        "",
        "---",
        "",
        "## FAITS mesurés",
        "",
    ]
    for fact in analysis["facts"]:
        lines.append(f"- {fact}")

    lines += ["", "## OBSERVATIONS", ""]
    if analysis["observations"]:
        for obs in analysis["observations"]:
            lines.append(f"- {obs}")
    else:
        lines.append("- Aucune observation particulière.")

    lines += ["", "## RISQUES identifiés", ""]
    for risk in analysis["risks"]:
        lines.append(f"⚠️ {risk}")

    lines += ["", "## LEÇONS déclenchées (sur faits)", ""]
    if analysis["lessons"]:
        for lesson in analysis["lessons"]:
            lines.append(f"📌 {lesson}")
    else:
        lines.append("- Aucune leçon connue déclenchée par les faits de cette session.")

    lines += ["", "## ACTIONS recommandées", ""]
    for action in analysis["actions"]:
        lines.append(f"→ {action}")

    lines += [
        "",
        "## Commits de la session",
        "",
    ]
    for c in git["commits"]:
        lines.append(f"- `{c['sha']}` {c['msg']}")

    if tests.get("status") not in ("not_measured", None) and tests.get("source"):
        lines += ["", f"*Tests lus depuis : `{tests['source']}`*"]

    lines += [
        "",
        "---",
        "",
        f"*Généré par `artcb_r392_auto_feedback.py` v{MODULE_VERSION} — R394-D — {ts.isoformat()}*",
        "",
        "### Intégration automatique (R394-C)",
        "",
        "Pour déclencher ce script automatiquement à chaque fin de session Bob IDE,",
        "ajouter dans `.bob/hooks/stop.py` :",
        "",
        "```python",
        "import subprocess, os",
        "repo = os.environ.get('ARTCB_REPO_PATH', os.getcwd())",
        "subprocess.run([",
        "    'python3', 'scripts/artcb_r392_auto_feedback.py', '--since', 'HEAD~1'",
        "], cwd=repo, timeout=30)",
        "```",
    ]

    content = "\n".join(lines)

    report_dir = repo / "rapports"
    report_dir.mkdir(exist_ok=True)
    fname = f"RETRO_{ts.strftime('%Y-%m-%d')}_{git['current_sha']}.md"
    out_path = report_dir / fname
    out_path.write_text(content, encoding="utf-8")
    print(f"[R392] Rétrospective générée : rapports/{fname}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="R392 — Auto-feedback post-tâche (faits réels)")
    parser.add_argument("--since", default=None,
                        help="SHA de référence (ex: HEAD~5, abc1234)")
    parser.add_argument("--test-results", default=None,
                        help="Chemin vers un JSON de résultats pytest")
    args = parser.parse_args()

    generate_report(args.since, args.test_results, REPO_ROOT)


if __name__ == "__main__":
    main()
