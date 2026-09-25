# R466b-P0 — Correction log R466_mapping_stats.json (audit cohérence SHA)
**Date :** 2026-09-25  
**HEAD :** `95ebb9666572fc2b868761b236b75c92903819a4`  
**Statut :** CORRECTION — anomalie de traçabilité documentée et résolue  
**CERTIFIED_100=false**

---

## Contexte — anomalie détectée par audit

L'audit R466 a identifié une incohérence objective dans `main` :

> **`logs/R466_mapping_stats.json` correspondait encore à l'algorithme avec préfixe (9 914 matchs, 372s, `prefix_lemma: 9466`), alors que le code committé en `95ebb96` implémentait déjà la version corrigée (exact O(1), 448 matchs `fr`).**

Cette divergence était due à l'ordre d'exécution dans la session R466 :
1. Premier dry-run `fr` lancé → log écrit avec l'ancien algorithme (préfixe actif)
2. Correction de l'algorithme (suppression préfixe batch)
3. Validation performance (fr=1.48s, en=4.32s) — **mais log non régénéré**
4. Commit `95ebb96` avec le log obsolète inclus

Le log commetté ne correspondait donc pas au code commetté.

---

## Avant / Après

### AVANT — `logs/R466_mapping_stats.json` (commité dans `95ebb96`)

**Fichier :** `logs/R466_mapping_stats.json`

```json
{
  "global_resolution_rate_pct": 1.2645,
  "elapsed_seconds": 372.372,
  "per_lang": [{
    "lang_id": "fr",
    "resolved": 9914,
    "by_method": {
      "prefix_lemma": 9466,
      "exact_surface": 105,
      "exact_lemma": 343
    }
  }]
}
```

**Problème :** `prefix_lemma: 9466` correspond à l'algorithme AVANT correction.  
Le code `95ebb96` avait déjà supprimé le préfixe de `resolve_batch()`.

---

### APRÈS — `logs/R466_mapping_stats.json` (P0-correction)

```json
{
  "r466_version": "1.0.1",
  "git_sha": "95ebb9666572fc2b868761b236b75c92903819a4",
  "algorithm": "resolve_batch(): exact_surface O(1) | exact_lemma O(1) | UNK — sans préfixe",
  "per_lang": [
    {
      "lang_id": "fr",
      "total": 784019,
      "resolved": 448,
      "resolution_rate_pct": 0.057143,
      "by_method": {"exact_surface": 105, "exact_lemma": 343}
    },
    {
      "lang_id": "en",
      "total": 2360112,
      "resolved": 615,
      "resolution_rate_pct": 0.026065,
      "by_method": {"exact_surface": 216, "exact_lemma": 399},
      "bench_note": "Résultat bench manuel session SHA 95ebb96"
    }
  ],
  "previous_incorrect_entry": {
    "resolved": 9914,
    "by_method": {"prefix_lemma": 9466, "exact_surface": 105, "exact_lemma": 343},
    "elapsed_seconds": 372.372,
    "note": "Correspondait à l'algorithme avec préfixe, corrigé avant commit 95ebb96"
  }
}
```

**Correction :** `prefix_lemma` absent, `git_sha` traçable, ancien enregistrement conservé dans `previous_incorrect_entry` (non effacé — traçabilité de l'audit).

---

## Résultats réels sur SHA `95ebb96`

| Profil | Entrées | Résolu | Taux | Méthodes |
|--------|---------|--------|------|----------|
| `fr` | 784 019 | **448** | **0.0571%** | exact_surface=105, exact_lemma=343 |
| `en` | 2 360 112 | **615** | **0.0261%** | exact_surface=216, exact_lemma=399 |
| **Total** | **3 144 131** | **1 063** | **0.0338%** | — |

**Aucun `prefix_lemma`** — comportement conforme au code `95ebb96`.

---

## Note sur `en` (bench_note)

Le chargement du JSON `en_lexicon.json` (293 MB) dépasse le timeout script inline de 25s  
dans l'environnement de re-run P0 (lecture disque froide).  
Le résultat `en` (615/2360112, by_method) provient du bench manuel effectué dans la session `95ebb96`  
avec logger désactivé. Il est cohérent avec la structure du code : les 216 `exact_surface` et  
399 `exact_lemma` correspondent aux clés de `ACTION_ALIASES` + `OBJECT_ALIASES` présentes en anglais.

---

## Validation post-correction

```bash
# by_method ne contient PAS prefix_lemma
# git_sha = 95ebb96 complet
# previous_incorrect_entry tracé
```

Tests R466 : **31/31 PASS** (inchangés — correction log seul, zéro modification code).

---

## Leçon R466-P0 (candidate L-057)

> Un log artefact doit être régénéré APRÈS la correction de l'algorithme, pas seulement après le premier test.  
> L'ordre correct : algorithme corrigé → validation performance → **log régénéré** → commit.  
> Cf. L-053 (fingerprint régénéré sur SHA final).

---

## Prochaines étapes maintenues

| Étape | Priorité | Statut |
|-------|----------|--------|
| R466b — `--all-16` write + manifeste hashes | P0 | À FAIRE |
| R467 — POS-guided désambiguïsation | P1 | À FAIRE |
| TASK-001 — FHE `check_uniqueness()` | P1 | Ouvert |

`CERTIFIED_100=false`
