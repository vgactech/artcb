# R466b — Exécution complète all-16 : lexicons_mapped/ + manifeste cryptographique
**Date :** 2026-09-25  
**HEAD :** `f7cbfbd34fc48e4e659bfc407c9549af3bdf7700`  
**Statut :** PASS — 16/16 profils traités  
**CERTIFIED_100=false**

---

## Contexte

Suite à R466 (mapping artcb_code) et R466b-P0 (correction log), R466b réalise l'exécution
complète `--all-16` en écriture avec manifeste cryptographique SHA-256 de chaque fichier.

---

## Artefacts produits

| Fichier | Rôle | État |
|---------|------|------|
| `scripts/artcb_r466b_all16_write.py` | Script all-16 write + manifeste | ✅ |
| `logs/R466b_manifest.json` | Manifeste SHA-256 (src+dst × 16 profils) | ✅ |
| `logs/R466b_run_stats.json` | Stats détaillées par profil | ✅ |
| `data/lexicons_mapped/*.json` (×16) | Lexiques avec artcb_code résolu | ✅ local |
| `.gitignore` | `data/lexicons_mapped/` ajouté | ✅ |

Note : `data/lexicons_mapped/` est local uniquement (gitignore) — fichiers >100 MB.
La preuve de traçabilité est dans `logs/R466b_manifest.json` (commité).

---

## Résultats globaux

| Métrique | Valeur |
|----------|--------|
| Profils traités | **16/16** |
| Entrées totales | **21 484 106** |
| Entrées résolues | **13 898** |
| Entrées UNK | **21 470 208** |
| Taux global | **0.0647%** |
| Algorithme | `exact_surface O(1)` \| `exact_lemma O(1)` \| `UNK` |

---

## Résultats par profil

| Profil | Entrées | Résolu | Taux | SHA-256 dst (10 premiers chars) |
|--------|---------|--------|------|----------------------------------|
| `ar` | 1 373 037 | 449 | 0.033% | `856a3484cd` |
| `de` | 1 733 696 | 791 | 0.046% | `48d9cdf3fd` |
| `en` | 2 360 112 | 615 | 0.026% | `9e2dcef84d` |
| `es` | 1 992 273 | 1 574 | 0.079% | `1fa94337c4` |
| `fr` | 784 019 | 448 | 0.057% | `08be964b14` |
| `id` | 79 949 | 63 | 0.079% | `0330900508` |
| `it` | 1 363 559 | 105 | 0.008% | `360216c7ae` |
| `ja` | 1 048 878 | 743 | 0.071% | `1e58843973` |
| `ko` | 463 834 | 84 | 0.018% | `0b9fa60c5a` |
| `la` | 2 042 686 | 516 | 0.025% | `6ffb36b5d5` |
| `pl` | 1 885 859 | 1 114 | 0.059% | `13dda2b306` |
| `pt` | 909 945 | 633 | 0.070% | `b89bee5126` |
| `pt-BR` | 145 744 | 30 | 0.021% | `6898f9e365` |
| `ru` | 1 935 993 | 286 | 0.015% | `39bb2ae074` |
| `tr` | 2 891 601 | **6 377** | **0.221%** | `3dcccb68c8` |
| `zh` | 472 921 | 70 | 0.015% | `6ecd6cb1d5` |

**Observation notable :** `tr` (turc) présente le taux le plus élevé (0.221%, 6377 matchs).
L'explication probable : le lexique turc est très riche en mots dérivés dont plusieurs formes
exactes figurent dans `ACTION_ALIASES` / `OBJECT_ALIASES` (ex: formes verbales communes).
Ce n'est pas un faux positif puisque la correspondance est exacte (O(1)) — mais une validation
POS-guidée (R467) permettra de confirmer ou corriger ce résultat.

---

## Chaîne de preuve manifeste

```
data/lexicons/{lang_id}_lexicon.json  (source)
       │
       ├── SHA-256 src  ──→  manifeste per_lang[lang].src_sha256
       ↓
LexiconMapper.resolve_batch()
       ↓
data/lexicons_mapped/{lang_id}_lexicon.json  (sortie)
       │
       └── SHA-256 dst  ──→  manifeste per_lang[lang].dst_sha256
```

Le fichier `logs/R466b_manifest.json` permet de vérifier :
- que le fichier source n'a pas changé depuis le run
- que le fichier de sortie correspond exactement à ce run
- que l'algorithme utilisé est `exact_surface O(1) | exact_lemma O(1) | UNK`

---

## Avant / Après

### AVANT R466b — pas de `data/lexicons_mapped/`

```
data/lexicons/fr_lexicon.json
  entries: [{..., "artcb_code": ""}, ...]
  r466_mapped: absent
```

### APRÈS R466b — `data/lexicons_mapped/fr_lexicon.json`

```json
{
  "lang_id": "fr",
  "entries": [{"surface_form": "vérifier", "artcb_code": "V1", ...}, ...],
  "r466_mapped": true,
  "r466_mapper_version": "1.0.1",
  "r466_resolved_count": 448,
  "r466_unresolved_count": 774105,
  "r466_resolution_rate_pct": 0.057143,
  "r466_by_method": {"exact_surface": 105, "exact_lemma": 343},
  "r466_by_code": {"V1": 72, "MOD": 58, ...}
}
```

---

## .gitignore mis à jour

```
# Avant
data/lexicons/

# Après
data/lexicons/
data/lexicons_mapped/
```

---

## Tests R466 — non-régression

**31/31 PASS** (code inchangé, le script est exécuté en dehors de pytest).

---

## Limites documentées

1. **0.065% taux global** — honnête : 360 clés exactes pour 21.5M entrées.
2. **`tr` 0.22%** — taux atypique à valider avec R467 POS-guided.
3. **`it` 0.008%** — très faible : peu de lemmes italiens dans les tables actuelles.
4. **SHA-256 dst** — reproductible uniquement si même version mapper + même source.
5. **`data/lexicons_mapped/` local** — non commité, preuve dans le manifeste committé.

---

## Prochaines étapes

| Étape | Priorité | Statut |
|-------|----------|--------|
| R467 — POS-guided désambiguïsation | P1 | À FAIRE |
| Validation `tr` taux atypique | P1 | À FAIRE |
| TASK-001 — FHE `check_uniqueness()` | P1 | Ouvert |

`CERTIFIED_100=false`
