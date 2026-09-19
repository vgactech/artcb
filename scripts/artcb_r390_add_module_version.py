#!/usr/bin/env python3
"""
R390 — Ajout automatique de MODULE_VERSION dans chaque module Python de src/.

Usage:
    python3 scripts/artcb_r390_add_module_version.py [--dry-run] [--version 1.0.0]

Stratégie :
  - Cherche la première ligne non-commentaire non-docstring non-encoding
  - Si MODULE_VERSION absent : insère "MODULE_VERSION = '1.0.0'  # R390"
  - Sauvegarde .bak si demandé
  - Rapport JSON en sortie

CERTIFIED_100=false | DEBUG MODE
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent / "src"
VERSION_LINE_PATTERN = re.compile(r"^MODULE_VERSION\s*=")
ENCODING_PATTERN = re.compile(r"^#.*coding[:=]")
SHEBANG_PATTERN = re.compile(r"^#!")
SKIP_FILES = {"__init__.py"}  # __init__ déjà géré via __version__


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


def patch_file(path: Path, version: str, dry_run: bool) -> dict:
    """Ajoute MODULE_VERSION si absent. Retourne un dict de résultat."""
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    lines = content.splitlines(keepends=True)

    # Déjà présent ?
    for line in lines:
        if VERSION_LINE_PATTERN.match(line.strip()):
            return {"path": str(path), "action": "skip_already_present"}

    insert_at = find_insert_line(lines)
    version_line = f"MODULE_VERSION = '{version}'  # R390 — auto-versioning\n"
    new_lines = lines[:insert_at] + [version_line] + lines[insert_at:]
    new_content = "".join(new_lines)

    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

    return {
        "path": str(path),
        "action": "patched" if not dry_run else "dry_run",
        "insert_at_line": insert_at + 1,
    }


def main():
    parser = argparse.ArgumentParser(description="R390 — Add MODULE_VERSION to all src/*.py")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas écrire, afficher seulement")
    parser.add_argument("--version", default="1.0.0", help="Version à insérer (défaut: 1.0.0)")
    args = parser.parse_args()

    results = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if "__pycache__" not in d]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            if fn in SKIP_FILES:
                continue
            path = Path(root) / fn
            result = patch_file(path, args.version, args.dry_run)
            results.append(result)

    patched = [r for r in results if r["action"] in ("patched", "dry_run")]
    skipped = [r for r in results if r["action"] == "skip_already_present"]

    summary = {
        "ts_ns": time.time_ns(),
        "version": args.version,
        "dry_run": args.dry_run,
        "total": len(results),
        "patched": len(patched),
        "skipped_already_present": len(skipped),
        "results": results,
    }

    report_path = Path("logs") / "R390_module_version_patch.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[R390] total={len(results)} patched={len(patched)} skipped={len(skipped)}")
    print(f"[R390] Rapport: {report_path}")
    if args.dry_run:
        print("[R390] Mode DRY-RUN — aucun fichier modifié")


if __name__ == "__main__":
    main()
