#!/usr/bin/env python3
"""
R405 — Installation du hook git pre-commit ARTCB (versioning automatique).

Ce script copie scripts/artcb_r405_precommit_hook.sh dans .git/hooks/pre-commit
et le rend exécutable.

Usage :
    python3 scripts/artcb_r405_install_precommit_hook.py
    python3 scripts/artcb_r405_install_precommit_hook.py --check   # vérifie sans installer
    python3 scripts/artcb_r405_install_precommit_hook.py --remove  # désinstalle le hook

Prérequis :
    - scripts/artcb_bump_module_version.py doit exister
    - doit être exécuté depuis la racine du dépôt git ARTCB

CERTIFIED_100=false | DEBUG MODE | R405
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R405 — installation hook pre-commit

import argparse
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HOOK_SOURCE = Path("scripts/artcb_r405_precommit_hook.sh")
HOOK_DEST_REL = Path(".git/hooks/pre-commit")
BUMP_SCRIPT = Path("scripts/artcb_bump_module_version.py")

# Marqueur d'identité pour détecter notre hook vs un hook existant tiers
HOOK_MARKER = "R405 — ARTCB pre-commit hook"


def get_repo_root() -> Path:
    """Retourne la racine du dépôt git."""
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
        ).strip()
        return Path(root)
    except subprocess.CalledProcessError as exc:
        print(f"ERREUR: pas dans un dépôt git ({exc})", file=sys.stderr)
        sys.exit(1)


def check_prerequisites(repo_root: Path) -> list[str]:
    """Vérifie les prérequis et retourne la liste des problèmes."""
    issues = []
    if not (repo_root / HOOK_SOURCE).exists():
        issues.append(f"Source manquante: {HOOK_SOURCE}")
    if not (repo_root / BUMP_SCRIPT).exists():
        issues.append(f"Script bump manquant: {BUMP_SCRIPT}")
    return issues


def is_our_hook(hook_path: Path) -> bool:
    """Vérifie si le hook existant est le nôtre (contient le marqueur R405)."""
    if not hook_path.exists():
        return False
    try:
        content = hook_path.read_text(encoding="utf-8", errors="ignore")
        return HOOK_MARKER in content
    except OSError:
        return False


def install(repo_root: Path, force: bool = False) -> int:
    """Installe le hook. Retourne 0=succès, 1=erreur."""
    hook_dest = repo_root / HOOK_DEST_REL

    # Vérification prérequis
    issues = check_prerequisites(repo_root)
    if issues:
        for issue in issues:
            print(f"[R405] ERREUR: {issue}", file=sys.stderr)
        return 1

    # Hook déjà présent et pas le nôtre → refus sans --force
    if hook_dest.exists() and not is_our_hook(hook_dest):
        if not force:
            print(
                f"[R405] WARN: Un hook pre-commit tiers existe déjà dans {hook_dest}.\n"
                "       Utiliser --force pour le remplacer.",
                file=sys.stderr,
            )
            return 1
        print(f"[R405] WARN: Remplacement d'un hook tiers existant (--force)", file=sys.stderr)

    # Copie + permissions
    source = repo_root / HOOK_SOURCE
    shutil.copy2(source, hook_dest)
    hook_dest.chmod(
        hook_dest.stat().st_mode
        | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )

    print(f"[R405] ✅ Hook installé: {hook_dest}")
    print(f"       Source: {source}")
    print(f"       Désormais, chaque 'git commit' bumpe automatiquement MODULE_VERSION")
    print(f"       des fichiers .py stagés qui contiennent MODULE_VERSION.")
    return 0


def check_status(repo_root: Path) -> int:
    """Affiche l'état du hook. Retourne 0 si installé, 1 sinon."""
    hook_dest = repo_root / HOOK_DEST_REL
    if not hook_dest.exists():
        print("[R405] ❌ Hook non installé (.git/hooks/pre-commit absent)")
        return 1
    if is_our_hook(hook_dest):
        perms = oct(hook_dest.stat().st_mode)[-3:]
        print(f"[R405] ✅ Hook R405 installé ({hook_dest}, perms={perms})")
        # Vérifie que le script bump est accessible
        if not (repo_root / BUMP_SCRIPT).exists():
            print(f"[R405] ⚠️  WARN: {BUMP_SCRIPT} manquant — hook installé mais inefficace")
            return 1
        return 0
    print("[R405] ⚠️  Hook présent mais TIERS (pas le nôtre). Utiliser --force pour installer.")
    return 1


def remove(repo_root: Path) -> int:
    """Désinstalle le hook si c'est le nôtre."""
    hook_dest = repo_root / HOOK_DEST_REL
    if not hook_dest.exists():
        print("[R405] Hook absent — rien à supprimer")
        return 0
    if not is_our_hook(hook_dest):
        print("[R405] WARN: Le hook existant n'est pas le nôtre — suppression refusée", file=sys.stderr)
        return 1
    hook_dest.unlink()
    print(f"[R405] 🗑️  Hook supprimé: {hook_dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R405 — Installation hook git pre-commit ARTCB (versioning auto)"
    )
    parser.add_argument("--check", action="store_true", help="Vérifie l'état sans installer")
    parser.add_argument("--remove", action="store_true", help="Désinstalle le hook")
    parser.add_argument("--force", action="store_true", help="Remplace un hook tiers existant")
    args = parser.parse_args(argv)

    repo_root = get_repo_root()
    print(f"[R405] Racine dépôt: {repo_root}")

    if args.remove:
        return remove(repo_root)
    if args.check:
        return check_status(repo_root)

    return install(repo_root, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
