#!/usr/bin/env python3
"""
R400-B — Auto-bump MODULE_VERSION (PATCH +1) après modification d'un module.

Usage :
    python3 scripts/artcb_bump_module_version.py <module_path> [--reason "R4xx description"] [--dry-run]
    python3 scripts/artcb_bump_module_version.py src/artcb/identity/biometric_onchain.py --reason "R401 forensic hardening"

Comportement :
    1. Lit MODULE_VERSION = 'X.Y.Z' dans le fichier cible.
    2. Bump PATCH : X.Y.Z → X.Y.(Z+1).
    3. Met à jour la ligne MODULE_VERSION dans le fichier (in-place, atomic).
    4. Calcule SHA-256 avant et après modification.
    5. Append dans data/trace/module_version_history.jsonl :
       {timestamp_ns, module, previous_version, new_version, bump, reason, git_sha, sha256_before, sha256_after}

Invariants :
    - Ne modifie PAS d'autre ligne que MODULE_VERSION.
    - Si MODULE_VERSION absent → erreur explicite, pas de stub.
    - Journal append-only (jamais écrasé).
    - CERTIFIED_100=false.

CERTIFIED_100=false | DEBUG MODE
"""
from __future__ import annotations

MODULE_VERSION = '1.0.1'  # R400-B — créé pour TASK-VERSIONING

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
HISTORY_FILE = REPO_ROOT / "data" / "trace" / "module_version_history.jsonl"
VERSION_RE = re.compile(r"^(MODULE_VERSION\s*=\s*['\"])(\d+\.\d+\.\d+)(['\"].*)$")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_sha(short: bool = True) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short" if short else "", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=str(REPO_ROOT)
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _bump_patch(version: str) -> str:
    """'1.2.3' → '1.2.4'"""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Version malformée : '{version}' (attendu X.Y.Z)")
    major, minor, patch = parts
    return f"{major}.{minor}.{int(patch) + 1}"


def _find_version_line(lines: list[str]) -> int | None:
    """Retourne l'index de la ligne MODULE_VERSION, ou None."""
    for i, line in enumerate(lines):
        if VERSION_RE.match(line.rstrip("\n")):
            return i
    return None


def _append_history(entry: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Core ────────────────────────────────────────────────────────────────────

def bump_module(module_path: str | Path, reason: str = "", dry_run: bool = False) -> dict:
    """
    Bump le PATCH de MODULE_VERSION dans module_path.
    Retourne un dict avec les détails de l'opération.
    Lance RuntimeError si MODULE_VERSION absent ou version malformée.
    """
    path = Path(module_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Module introuvable : {path}")

    # --- Lecture et parsing ------------------------------------------------
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    idx = _find_version_line(lines)

    if idx is None:
        try:
            path_display = str(path.relative_to(REPO_ROOT))
        except ValueError:
            path_display = str(path)
        raise RuntimeError(
            f"MODULE_VERSION introuvable dans {path_display}\n"
            f"  Ajouter : MODULE_VERSION = '1.0.0'  # R<n> — <raison>"
        )

    line = lines[idx].rstrip("\n")
    m = VERSION_RE.match(line)
    assert m, f"Regex ne match pas la ligne : '{line}'"
    prefix, old_version, suffix = m.group(1), m.group(2), m.group(3)
    new_version = _bump_patch(old_version)

    # --- SHA avant ---------------------------------------------------------
    sha256_before = _sha256_file(path)
    try:
        rel = str(path.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(path)

    if dry_run:
        print(f"[DRY-RUN] {rel}: {old_version} → {new_version}")
        return {
            "dry_run": True,
            "module": rel,
            "previous_version": old_version,
            "new_version": new_version,
            "sha256_before": sha256_before,
            "sha256_after": sha256_before,
        }

    # --- Mise à jour in-place (atomic write) --------------------------------
    # Conserver commentaire existant, remplacer uniquement le numéro de version
    new_line = f"{prefix}{new_version}{suffix}\n"
    lines[idx] = new_line

    # Écriture atomique via fichier temporaire
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(path)  # atomic on POSIX

    sha256_after = _sha256_file(path)

    # --- Journal append-only ------------------------------------------------
    git_sha = _git_sha()
    try:
        module_str = str(path.relative_to(REPO_ROOT))
    except ValueError:
        module_str = str(path)
    entry = {
        "timestamp_ns": time.time_ns(),
        "module": module_str,
        "previous_version": old_version,
        "new_version": new_version,
        "bump": "PATCH",
        "reason": reason or "manual bump",
        "git_sha": git_sha,
        "sha256_before": sha256_before,
        "sha256_after": sha256_after,
    }
    _append_history(entry)

    print(
        f"[ARTCB BUMP] {rel}: "
        f"{old_version} → {new_version}  (git={git_sha})"
    )
    return entry


# ── Bulk mode : bump tous les modules modifiés depuis un SHA ────────────────

def bump_modified_since(since_sha: str, reason: str = "", dry_run: bool = False) -> list[dict]:
    """
    Bumpe tous les modules Python modifiés depuis since_sha qui contiennent MODULE_VERSION.
    Retourne la liste des entrées produites.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", since_sha, "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=str(REPO_ROOT)
        )
        files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip().endswith(".py")]
    except Exception as e:
        raise RuntimeError(f"Impossible de lister les fichiers modifiés : {e}") from e

    entries = []
    skipped = []
    errors = []

    for rel_path in files:
        full_path = REPO_ROOT / rel_path
        if not full_path.exists():
            skipped.append(rel_path)
            continue
        try:
            entry = bump_module(full_path, reason=reason, dry_run=dry_run)
            entries.append(entry)
        except RuntimeError as e:
            # MODULE_VERSION absent — skip silencieux mais tracé
            skipped.append(f"{rel_path} (sans MODULE_VERSION)")
        except Exception as e:
            errors.append(f"{rel_path}: {e}")

    if skipped:
        print(f"[ARTCB BUMP] Skipped ({len(skipped)}) : {', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''}")
    if errors:
        print(f"[ARTCB BUMP] Erreurs ({len(errors)}) : {'; '.join(errors)}")

    return entries


# ── CLI ─────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Bump PATCH de MODULE_VERSION + journal module_version_history.jsonl"
    )
    p.add_argument("module", nargs="?", help="Chemin du module Python à bumper")
    p.add_argument("--reason", "-r", default="", help="Raison du bump (ex: 'R401 forensic')")
    p.add_argument("--since", "-s", default="", help="SHA git depuis lequel détecter les modules modifiés")
    p.add_argument("--dry-run", "-n", action="store_true", help="Simule sans modifier ni écrire dans le journal")
    p.add_argument("--show-history", action="store_true", help="Affiche les 20 dernières entrées du journal")
    return p.parse_args(argv)


def _show_history(n: int = 20) -> None:
    if not HISTORY_FILE.exists():
        print("[ARTCB BUMP] Aucun historique trouvé.")
        return
    lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    recent = lines[-n:] if len(lines) > n else lines
    print(f"[ARTCB BUMP] Journal ({len(lines)} entrée(s) totales — {len(recent)} affichées) :")
    for line in recent:
        try:
            e = json.loads(line)
            print(f"  {e['module']:60s}  {e['previous_version']} → {e['new_version']}  [{e['reason'][:40]}]  git={e['git_sha']}")
        except Exception:
            print(f"  (ligne malformée: {line[:80]})")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.show_history:
        _show_history()
        return 0

    if args.since:
        entries = bump_modified_since(args.since, reason=args.reason, dry_run=args.dry_run)
        print(f"[ARTCB BUMP] {len(entries)} module(s) bumpé(s).")
        return 0

    if not args.module:
        print("ERREUR : spécifier un module ou --since <sha>. Utiliser --help.", file=sys.stderr)
        return 1

    try:
        bump_module(args.module, reason=args.reason, dry_run=args.dry_run)
        return 0
    except (FileNotFoundError, RuntimeError) as e:
        print(f"ERREUR : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
