#!/usr/bin/env bash
# R405 — ARTCB pre-commit hook : auto-bump MODULE_VERSION sur les .py stagés
#
# Comportement :
#   1. Récupère la liste des fichiers .py ajoutés/modifiés dans le stage (git diff --cached)
#   2. Pour chaque fichier contenant MODULE_VERSION = 'X.Y.Z', appelle
#      artcb_bump_module_version.py <fichier> --reason "pre-commit auto-bump"
#   3. Re-stage le fichier bumpé (git add) pour que le bump soit inclus dans le commit
#   4. FAIL-OPEN : si le script échoue (absent, erreur Python, etc.), affiche un
#      avertissement mais ne bloque JAMAIS le commit
#
# Installation automatique via scripts/artcb_r405_install_precommit_hook.py
# Ne pas modifier manuellement — régénérer avec le script d'installation.
#
# CERTIFIED_100=false | DEBUG MODE | R405

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
BUMP_SCRIPT="$REPO_ROOT/scripts/artcb_bump_module_version.py"
REASON="pre-commit auto-bump R405"

# Vérifie que le script de bump existe
if [ ! -f "$BUMP_SCRIPT" ]; then
    echo "[R405-hook] WARN: artcb_bump_module_version.py absent — skip versioning" >&2
    exit 0
fi

# Liste les .py stagés (ajoutés A ou modifiés M)
STAGED_PY=$(git diff --cached --name-only --diff-filter=AM | grep '\.py$' || true)

if [ -z "$STAGED_PY" ]; then
    # Aucun .py stagé — rien à bumper
    exit 0
fi

BUMPED=0
SKIPPED=0
ERRORS=0

while IFS= read -r filepath; do
    # Chemin absolu
    abs_path="$REPO_ROOT/$filepath"
    
    if [ ! -f "$abs_path" ]; then
        continue
    fi
    
    # Vérifie si le fichier contient MODULE_VERSION
    if ! grep -q "^MODULE_VERSION" "$abs_path" 2>/dev/null; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi
    
    # Bump PATCH via le script Python (fail-open)
    if python3 "$BUMP_SCRIPT" "$abs_path" --reason "$REASON" 2>/dev/null; then
        # Re-stage le fichier bumpé pour inclure le changement de version dans le commit
        git add "$abs_path"
        BUMPED=$((BUMPED + 1))
        echo "[R405-hook] bumped: $filepath" >&2
    else
        ERRORS=$((ERRORS + 1))
        echo "[R405-hook] WARN: bump failed for $filepath (skipped)" >&2
    fi
done <<< "$STAGED_PY"

if [ "$BUMPED" -gt 0 ] || [ "$ERRORS" -gt 0 ]; then
    echo "[R405-hook] summary: bumped=$BUMPED skipped=$SKIPPED errors=$ERRORS" >&2
fi

# Toujours exit 0 — ne jamais bloquer un commit (fail-open)
exit 0
