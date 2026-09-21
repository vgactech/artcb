# R405 — TASK-VERSIONING : hook git pre-commit auto-bump MODULE_VERSION

**Date :** 2026-09-21  
**SHA HEAD :** `34a89a9` (avant commit R405 final)  
**Statut :** ✅ DONE — commité + pushé  
**CERTIFIED_100 :** false  

---

## Contexte

TASK-VERSIONING était ouverte depuis R400-B : le script `artcb_bump_module_version.py`
existait mais son appel restait **manuel**. Aucun git hook `pre-commit` n'était présent.
R405 ferme ce chantier en rendant le bump **automatique et systématique** à chaque `git commit`.

---

## AVANT / APRÈS

### AVANT (avant R405)

```
git commit
      ↓
aucun hook pre-commit
      ↓
MODULE_VERSION jamais bumpé automatiquement
      ↓
divergence entre version déclarée et code réel
```

Fichier `.git/hooks/pre-commit` : **absent**

### APRÈS (R405)

```
git commit
      ↓
.git/hooks/pre-commit (R405)
      ↓
git diff --cached --name-only → fichiers .py stagés
      ↓
pour chaque fichier contenant MODULE_VERSION :
    artcb_bump_module_version.py <fichier>
    git add <fichier>  (re-stage le bump)
      ↓
commit inclut version bumpée
      ↓
journal data/trace/module_version_history.jsonl mis à jour
```

---

## Fichiers créés

| Fichier | Description | Lignes |
|---|---|---|
| `scripts/artcb_r405_precommit_hook.sh` | Le hook bash installé dans `.git/hooks/pre-commit` | 62 |
| `scripts/artcb_r405_install_precommit_hook.py` | Script d'installation/vérification/désinstallation | 140 |
| `tests/test_r405_precommit_hook.py` | 15/15 PASS T01→T15 | 260 |

---

## Résultats des tests

```
tests/test_r405_precommit_hook.py — 15/15 PASS (11.40s)

T01–T04 : installer check/install/remove ✅
T05–T08 : hook bash (exit 0, bump, skip no-version, no-staged) ✅
T09–T12 : E2E réel (commit bumps version, committé en base, journal, multi-fichiers) ✅
T13–T15 : cas limites (non-.py, bump absent=fail-open, check retour 1) ✅
```

---

## Validation E2E (test réel exécuté pendant R405)

```
MODULE_VERSION = '2.0.0'  ← avant commit
[R405-hook] bumped: scripts/artcb_r405_hook_test_target.py
MODULE_VERSION = '2.0.1'  ← après commit automatique
```

---

## Propriétés garanties

| Propriété | Valeur |
|---|---|
| Fail-open | ✅ exit 0 toujours, même si bump script absent ou erreur |
| Seuls les `.py` | ✅ `--diff-filter=AM` sur `.py` uniquement |
| Seuls avec MODULE_VERSION | ✅ `grep -q "^MODULE_VERSION"` avant d'appeler |
| Re-stage automatique | ✅ `git add <fichier>` après bump |
| Journal append-only | ✅ `data/trace/module_version_history.jsonl` |
| Idempotent si pas de .py | ✅ exit silencieux |

---

## Utilisation

```bash
# Installer le hook (une seule fois par clone)
python3 scripts/artcb_r405_install_precommit_hook.py

# Vérifier que le hook est actif
python3 scripts/artcb_r405_install_precommit_hook.py --check

# Désinstaller (si nécessaire)
python3 scripts/artcb_r405_install_precommit_hook.py --remove
```

⚠️ **Important** : le hook est dans `.git/hooks/` (non tracké par git).
Tout nouveau clone du dépôt doit relancer l'installation.  
Un README note à ajouter : `make install-hooks` ou équivalent.

---

## Limites documentées

- `.git/hooks/` n'est pas versionné → chaque clone requiert `python3 scripts/artcb_r405_install_precommit_hook.py`
- Le bump est PATCH uniquement (X.Y.Z → X.Y.Z+1) — pour MINOR/MAJOR : appel manuel
- Un `.py` sans `MODULE_VERSION = '...'` est silencieusement ignoré (pas une erreur)

---

## CERTIFIED_100=false
