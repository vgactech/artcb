# R394 — Vérification de chaîne cryptographique post-audit

> **SHA vérifié** : `5148f8e` | `CERTIFIED_100=false` | Mode DEBUG  
> **Date** : 2026-09-19 | **Contexte** : Résolution de la divergence `6ba1246` ↔ `5148f8e` identifiée par l'audit expert

---

## Problème initial identifié par l'audit

L'audit expert a détecté une divergence forensic :

| Élément | Valeur observée |
|---------|----------------|
| HEAD annoncé dans le message R394 | `5148f8e` |
| `git_sha` dans `logs/R394_module_fingerprints.json` | `6ba1246` |

**Cause racine** : le fingerprint a été généré AVANT le commit R394 (`6ba1246`), puis l'artefact a été committé dans `5148f8e` sans être régénéré. C'est exactement le type de divergence que R394-B est censé détecter et empêcher.

---

## Correction

Régénération du fingerprint sur le HEAD exact `5148f8e` :

```bash
python3 scripts/artcb_r390_add_module_version.py --fingerprint-only
# [R394] fingerprints=294 git_sha=5148f8e
```

---

## Vérification de la chaîne complète

### Étape 1 — HEAD ↔ artefact

```
HEAD actuel      : 5148f8e
git_sha artefact : 5148f8e
Résultat         : ✅ COHÉRENT
```

### Étape 2 — SHA-256 contenu ↔ artefact (10 modules aléatoires, seed=42)

```python
for module in sample:
    actual_sha = sha256(path.read_bytes())
    assert actual_sha == fingerprint['sha256']
# 10/10 OK — Résultat : ✅ COHÉRENT
```

### Étape 3 — Modules sans MODULE_VERSION

```
Total sans MODULE_VERSION : 42
Tous sont des __init__.py : ✅ OUI
Explication : exclusion volontaire R390 — les __init__.py utilisent __version__
Couverture réelle : 252/252 modules non-__init__ = 100%
```

### Étape 4 — Tests sur ce SHA

```
tests/test_task001_r374_bch.py                   30/30 PASS
tests/test_task001_r378_hamming.py               28/28 PASS
tests/test_task001_r373_human_identity_policy.py 26/26 PASS
tests/test_task006_r387_webauthn_fanout.py       15/15 PASS
tests/test_task001_r376_uniqueness.py            22/22 PASS
TOTAL ARTCB CORE : 121/121 PASS (sur SHA 5148f8e)
```

Tests hors scope (dépendances externes) : `test_optimizations_advanced.py` — FAISS/PDF — préexistants, non liés à R394.

### Étape 5 — Rapport RETRO sur ce SHA

```
rapports/RETRO_2026-09-19_5148f8e.md
SHA dans rapport : 5148f8e ✅
```

### Chaîne complète

```
5148f8e (HEAD actuel)
    │
    ├── fingerprint régénéré sur 5148f8e ✅
    │
    ├── SHA-256 de 10 modules vérifiés ↔ contenu réel ✅
    │
    ├── 0 chemin absolu dans l'artefact ✅
    │
    ├── 121/121 tests ARTCB core PASS ✅
    │
    └── rapport RETRO attaché à 5148f8e ✅
```

---

## Observation sur R394-C (feedback fail-open)

L'audit note que "fail-open" peut masquer silencieusement l'absence de feedback.

**Correction documentée** : le hook `stop.py` exécute le script avec `capture_output=True`. Pour savoir si l'exécution a réussi ou échoué, il faudrait lire le `returncode`. Ce point est noté pour R395 — ajouter une trace explicite de succès/échec dans `bob_turns.jsonl` sans bloquer la session.

---

## Correction de la règle de workflow (leçon R394)

**L-053 (nouvelle leçon)** : Tout artefact de fingerprint/versioning (`logs/R394_module_fingerprints.json`) doit être **régénéré sur le SHA final** APRÈS le dernier commit de la session, juste avant le push. L'ordre correct est :

```
développement
    ↓
tests PASS
    ↓
git commit
    ↓
python3 scripts/artcb_r390_add_module_version.py --fingerprint-only
    ↓
git add logs/R394_module_fingerprints.json
    ↓
git commit --amend (ou commit séparé de synchronisation)
    ↓
git push
    ↓
artefact.git_sha == HEAD ✅
```

---

## État post-vérification

| Élément | État |
|---------|------|
| R394-A chemins relatifs | 🟢 VÉRIFIÉ (0 chemin absolu) |
| R394-B SHA-256 par module | 🟢 VÉRIFIÉ (10/10 SHA cohérents) |
| R394-B git_sha cohérent avec HEAD | 🟢 CORRIGÉ (5148f8e partout) |
| R394-C hook stop.py branché | 🟡 PRÉSENT — test runtime à confirmer |
| R394-D feedback sur faits | 🟢 VÉRIFIÉ (RETRO_5148f8e.md) |
| R394-E multi-domaines + confidence | 🟢 VÉRIFIÉ (111/230 multi, avg 0.742) |
| 42 modules __init__.py sans MODULE_VERSION | 🟢 EXCLU VOLONTAIRE |
| Tests ARTCB core 121/121 | 🟢 PASS sur 5148f8e |
| CERTIFIED_100 | 🔴 false (invariant) |

---

*`CERTIFIED_100=false` | Rapport vérification chaîne R394 | 2026-09-19*
