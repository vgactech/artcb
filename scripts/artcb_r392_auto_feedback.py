#!/usr/bin/env python3
"""
R392 — Auto-feedback automatique post-tâche ARTCB.

Mécanisme :
  - Appelé automatiquement dans le hook Bob IDE `stop.py` après chaque session
  - Lit les derniers commits git depuis le dernier checkpoint
  - Lit les derniers tests PASS/FAIL dans les logs pytest
  - Génère un fichier `rapports/RETRO_<date>_<sha>.md` avec :
      * Points forts (ce qui a bien marché)
      * Points faibles / risques identifiés
      * Métriques : tests PASS/FAIL, modules modifiés, couverture règles

Usage:
    python3 scripts/artcb_r392_auto_feedback.py [--since <sha>]
    python3 scripts/artcb_r392_auto_feedback.py --since HEAD~3

Le script est conçu pour tourner EN PARALLÈLE de la tâche principale (jamais bloquant).
Il ne modifie AUCUN fichier source — uniquement des rapports dans rapports/.

CERTIFIED_100=false | DEBUG MODE
"""

from __future__ import annotations

MODULE_VERSION = '1.0.0'  # R392 — auto-feedback

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: list[str], *, cwd: str | None = None, timeout: int = 15) -> str:
    """Exécute une commande, retourne stdout ou '' si erreur."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.stdout.strip()
    except Exception:
        return ""


def git_log_since(since_sha: str | None, repo: Path) -> list[dict]:
    """Retourne les commits depuis since_sha (ou les 5 derniers si None)."""
    ref = f"{since_sha}..HEAD" if since_sha else "-5"
    out = _run(
        ["git", "log", ref if ".." in str(ref) else f"-{ref.lstrip('-')}", "--oneline"],
        cwd=str(repo),
    )
    commits = []
    for line in out.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commits.append({"sha": parts[0], "msg": parts[1]})
    return commits


def git_diff_stats(since_sha: str | None, repo: Path) -> dict:
    """Statistiques de diff : fichiers modifiés, insertions, suppressions."""
    ref = f"{since_sha}..HEAD" if since_sha else "HEAD~1..HEAD"
    out = _run(["git", "diff", "--stat", ref], cwd=str(repo))
    lines = out.splitlines()
    summary = lines[-1] if lines else ""
    files_changed = [l.split("|")[0].strip() for l in lines if "|" in l]
    return {
        "summary": summary,
        "files_changed": files_changed,
        "files_count": len(files_changed),
    }


def read_latest_test_results(repo: Path) -> dict:
    """Cherche les derniers logs de tests dans logs/ pour extraire PASS/FAIL."""
    log_dir = repo / "logs"
    if not log_dir.exists():
        return {"status": "no_logs"}
    # Cherche les fichiers .txt ou .json récents contenant des résultats pytest
    candidates = sorted(log_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates[:5]:
        content = candidate.read_text(errors="ignore")
        if "passed" in content or "failed" in content:
            # Extraire la dernière ligne de résultat
            for line in reversed(content.splitlines()):
                if "passed" in line or "failed" in line:
                    return {"source": str(candidate.name), "result_line": line.strip()}
    return {"status": "not_found"}


def count_module_versions(src: Path) -> dict:
    """Compte les modules avec MODULE_VERSION."""
    total = 0
    versioned = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if "__pycache__" not in d]
        for fn in files:
            if fn.endswith(".py") and fn != "__init__.py":
                total += 1
                content = (Path(root) / fn).read_text(errors="ignore")
                if "MODULE_VERSION" in content:
                    versioned += 1
    return {"total": total, "versioned": versioned, "coverage_pct": round(100 * versioned / max(total, 1), 1)}


def analyze_commits(commits: list[dict]) -> dict:
    """Identifie points forts/faibles depuis les messages de commit."""
    strengths = []
    weaknesses = []
    for c in commits:
        msg = c["msg"].lower()
        if "pass" in msg or "fix" in msg or "r38" in msg or "r39" in msg:
            strengths.append(c["msg"])
        if "fail" in msg or "hotfix" in msg or "bug" in msg or "erreur" in msg:
            weaknesses.append(c["msg"])
    return {"strengths": strengths, "weaknesses": weaknesses}


def generate_retro_report(since_sha: str | None, repo: Path) -> Path:
    """Génère le rapport de rétrospective Markdown."""
    ts = datetime.now(timezone.utc)
    current_sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=str(repo)) or "unknown"
    commits = git_log_since(since_sha, repo)
    diff_stats = git_diff_stats(since_sha, repo)
    test_results = read_latest_test_results(repo)
    module_stats = count_module_versions(repo / "src")
    commit_analysis = analyze_commits(commits)

    # ── Contenu Markdown ────────────────────────────────────────────────────
    lines = [
        f"# Rétrospective ARTCB — {ts.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        f"> **SHA actuel** : `{current_sha}` | **Since** : `{since_sha or 'last 5 commits'}`",
        f"> `CERTIFIED_100=false` | Mode DEBUG",
        "",
        "## 1. Commits inclus dans cette session",
        "",
    ]
    if commits:
        for c in commits:
            lines.append(f"- `{c['sha']}` {c['msg']}")
    else:
        lines.append("- *(aucun commit depuis le point de référence)*")

    lines += [
        "",
        "## 2. Diff statistiques",
        "",
        f"- Résumé : `{diff_stats['summary']}`",
        f"- Fichiers touchés ({diff_stats['files_count']}) :",
        "",
    ]
    for fn in diff_stats["files_changed"][:20]:
        lines.append(f"  - `{fn}`")
    if diff_stats["files_count"] > 20:
        lines.append(f"  - *(+ {diff_stats['files_count'] - 20} autres)*")

    lines += [
        "",
        "## 3. Résultats de tests",
        "",
    ]
    if "result_line" in test_results:
        lines.append(f"- Source : `{test_results['source']}`")
        lines.append(f"- Résultat : `{test_results['result_line']}`")
    else:
        lines.append("- Aucun log de test récent trouvé dans `logs/`.")

    lines += [
        "",
        "## 4. Versioning modules (R390)",
        "",
        f"- Modules total : {module_stats['total']}",
        f"- Modules versionnés (MODULE_VERSION) : {module_stats['versioned']}",
        f"- Couverture : **{module_stats['coverage_pct']}%**",
        "",
        "## 5. Points forts identifiés",
        "",
    ]
    if commit_analysis["strengths"]:
        for s in commit_analysis["strengths"]:
            lines.append(f"✅ {s}")
    else:
        lines.append("*(à remplir manuellement ou enrichir le détecteur de patterns)*")

    lines += [
        "",
        "## 6. Points faibles / risques",
        "",
    ]
    if commit_analysis["weaknesses"]:
        for w in commit_analysis["weaknesses"]:
            lines.append(f"⚠️ {w}")
    else:
        lines.append("*(aucun pattern de faiblesse détecté dans les messages de commit)*")

    lines += [
        "",
        "## 7. Recommandations",
        "",
        "- Vérifier que `CERTIFIED_100=false` avant tout déploiement mainnet.",
        "- Tout commit ajoutant une lib dans `requirements.txt` → `pip install` sur les nœuds live (L-048).",
        "- `git status --short` doit être vide avant de marquer une tâche DONE (L-049).",
        "- `timeout_seconds` calibré au minimum réel : pytest ≤ 60s, push ≤ 30s (L-052).",
        "",
        "---",
        "",
        f"*Généré automatiquement par `artcb_r392_auto_feedback.py` — R392 — {ts.isoformat()}*",
    ]

    content = "\n".join(lines)

    # ── Sauvegarde ─────────────────────────────────────────────────────────
    report_dir = repo / "rapports"
    report_dir.mkdir(exist_ok=True)
    fname = f"RETRO_{ts.strftime('%Y-%m-%d')}_{current_sha}.md"
    out_path = report_dir / fname
    out_path.write_text(content, encoding="utf-8")

    print(f"[R392] Rétrospective générée : {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="R392 — Auto-feedback post-tâche ARTCB")
    parser.add_argument(
        "--since",
        default=None,
        help="SHA de référence depuis lequel analyser les commits (ex: HEAD~5)",
    )
    args = parser.parse_args()

    repo = Path(__file__).parent.parent
    generate_retro_report(args.since, repo)


if __name__ == "__main__":
    main()
