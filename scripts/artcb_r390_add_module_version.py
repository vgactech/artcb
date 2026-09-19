#!/usr/bin/env python3
"""
R390 — Ajout automatique de MODULE_VERSION dans chaque module Python de src/.
R394-A — Chemins relatifs dans le rapport (pas de /Users/xxx en dur).
R394-B — Fingerprint SHA-256 du contenu + git SHA pour vrai versioning lié au contenu.

Usage:
    python3 scripts/artcb_r390_add_module_version.py [--dry-run] [--version 1.0.0]
    python3 scripts/artcb_r390_add_module_version.py --fingerprint-only  (recalcule SHA sans patcher)

Stratégie :
  - Cherche la première ligne non-commentaire non-docstring non-encoding
  - Si MODULE_VERSION absent : insère "MODULE_VERSION = '1.0.0'  # R390"
  - Rapport JSON : chemins RELATIFS à la racine du dépôt (jamais de chemin absolu)
  - Fingerprint = SHA-256 du contenu du fichier après patch
  - git_sha = HEAD court au moment du patch

CERTIFIED_100=false | DEBUG MODE
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()
ROOT = REPO_ROOT / "src"
VERSION_LINE_PATTERN = re.compile(r"^MODULE_VERSION\s*=")
ENCODING_PATTERN = re.compile(r"^#.*coding[:=]")
SHEBANG_PATTERN = re.compile(r"^#!")
SKIP_FILES = {"__init__.py"}  # __init__ déjà géré via __version__


def _relative(path: Path) -> str:
    """Retourne le chemin RELATIF à REPO_ROOT. Jamais de /Users/xxx."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _git_sha() -> str:
    """SHA court du HEAD actuel, ou 'unknown'."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(REPO_ROOT)
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


FUTURE_IMPORT_PATTERN = re.compile(r"^from\s+__future__\s+import")


def find_insert_line(lines: list[str]) -> int:
    """Retourne l'index (0-based) où insérer MODULE_VERSION.

    Règle : après les lignes shebang/encoding/docstrings/commentaires d'en-tête
    ET après les éventuels 'from __future__ import' (obligatoirement en premier),
    mais AVANT les autres imports.
    """
    in_docstring = False
    docstring_char = None
    last_future_line = -1
    i = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Shebang / encoding en tête
        if i < 3 and (SHEBANG_PATTERN.match(stripped) or ENCODING_PATTERN.match(stripped)):
            continue
        # Triple-quote docstring module
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                triple = stripped[:3]
                rest = stripped[3:]
                if rest.endswith(triple) and len(rest) >= 3:
                    continue  # docstring sur une ligne
                in_docstring = True
                docstring_char = triple
                continue
        else:
            if docstring_char and docstring_char in stripped:
                in_docstring = False
                continue
            continue
        # from __future__ import — doit rester AVANT MODULE_VERSION
        if FUTURE_IMPORT_PATTERN.match(stripped):
            last_future_line = i
            continue
        # Commentaire
        if stripped.startswith("#"):
            continue
        # Ligne vide
        if not stripped:
            continue
        # Si on a vu des __future__, insérer après eux
        if last_future_line >= 0:
            return last_future_line + 1
        # Ligne de code : on insère ici
        return i
    # Si on atteint la fin avec des __future__
    if last_future_line >= 0:
        return last_future_line + 1
    return i + 1


def patch_file(path: Path, version: str, dry_run: bool, git_sha: str) -> dict:
    """Ajoute MODULE_VERSION si absent + fingerprint SHA-256 du contenu.

    Retourne un dict avec chemins RELATIFS uniquement (R394-A).
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        content_before = f.read()
    lines = content_before.splitlines(keepends=True)

    rel_path = _relative(path)  # R394-A : jamais de chemin absolu

    # Déjà présent ?
    for line in lines:
        if VERSION_LINE_PATTERN.match(line.strip()):
            return {
                "path": rel_path,
                "action": "skip_already_present",
                "sha256_current": _sha256(content_before),
                "git_sha": git_sha,
            }

    insert_at = find_insert_line(lines)
    version_line = f"MODULE_VERSION = '{version}'  # R390 — auto-versioning\n"
    new_lines = lines[:insert_at] + [version_line] + lines[insert_at:]
    new_content = "".join(new_lines)

    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

    return {
        "path": rel_path,                         # R394-A : relatif
        "action": "patched" if not dry_run else "dry_run",
        "insert_at_line": insert_at + 1,
        "sha256_before": _sha256(content_before), # R394-B : fingerprint avant
        "sha256_after": _sha256(new_content),     # R394-B : fingerprint après
        "git_sha": git_sha,                        # R394-B : contexte git
    }


def fingerprint_only(root: Path, git_sha: str) -> list[dict]:
    """Calcule uniquement les fingerprints sans modifier les fichiers."""
    results = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if "__pycache__" not in d]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = Path(r) / fn
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            has_version = any(
                VERSION_LINE_PATTERN.match(line.strip())
                for line in content.splitlines()
            )
            results.append({
                "path": _relative(path),
                "sha256": _sha256(content),
                "has_module_version": has_version,
                "git_sha": git_sha,
                "ts_ns": time.time_ns(),
            })
    return results


def main():
    parser = argparse.ArgumentParser(description="R390/R394 — MODULE_VERSION + fingerprints")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas écrire, afficher seulement")
    parser.add_argument("--version", default="1.0.0", help="Version à insérer (défaut: 1.0.0)")
    parser.add_argument("--fingerprint-only", action="store_true",
                        help="Recalculer SHA-256 sans patcher (R394-B)")
    args = parser.parse_args()

    git_sha = _git_sha()

    if getattr(args, "fingerprint_only", False):
        fp_results = fingerprint_only(ROOT, git_sha)
        report_path = Path("logs") / "R394_module_fingerprints.json"
        report_path.parent.mkdir(exist_ok=True)
        summary = {
            "ts_ns": time.time_ns(),
            "git_sha": git_sha,
            "repo_root": str(REPO_ROOT.name),  # Juste le nom, pas le chemin absolu
            "total": len(fp_results),
            "with_version": sum(1 for r in fp_results if r["has_module_version"]),
            "modules": fp_results,
        }
        with open(report_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"[R394] fingerprints={len(fp_results)} git_sha={git_sha}")
        print(f"[R394] Rapport: {report_path}")
        return

    results = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if "__pycache__" not in d]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            if fn in SKIP_FILES:
                continue
            path = Path(root) / fn
            result = patch_file(path, args.version, args.dry_run, git_sha)
            results.append(result)

    patched = [r for r in results if r["action"] in ("patched", "dry_run")]
    skipped = [r for r in results if r["action"] == "skip_already_present"]

    summary = {
        "ts_ns": time.time_ns(),
        "git_sha": git_sha,                     # R394-B
        "repo_root": str(REPO_ROOT.name),        # R394-A : nom uniquement, pas chemin absolu
        "version": args.version,
        "dry_run": args.dry_run,
        "total": len(results),
        "patched": len(patched),
        "skipped_already_present": len(skipped),
        "results": results,                      # R394-A : tous les chemins sont relatifs
    }

    report_path = Path("logs") / "R390_module_version_patch.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[R390] total={len(results)} patched={len(patched)} skipped={len(skipped)} git_sha={git_sha}")
    print(f"[R390] Rapport: {report_path}")
    if args.dry_run:
        print("[R390] Mode DRY-RUN — aucun fichier modifié")


if __name__ == "__main__":
    main()
