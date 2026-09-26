# R485 — Canonical Language Registry — Résolution divergence 14/16 langues
**Date :** 2026-09-26  
**SHA de référence :** 63bde4c (avant commit R485)  
**Auteur :** Bob IDE — Session R485  
**CERTIFIED_100 :** false (invariant absolu)  
**Mode :** DEBUG  

---

## 1. Contexte — Divergence identifiée par l'audit expert

L'audit GitHub a identifié trois états incompatibles dans le dépôt pour la déclaration de couverture linguistique :

| Artefact | Déclaration | Problème |
|----------|-------------|---------|
| `rules/ARTCB_14_LANGUAGES.json` | 14 (champs `null`) | Structure cassée — artefact historique inutilisable |
| `rules/artcd_language_registry.json` | 14 langues dont 7 `NOT_STARTED` | 7 langues marquées "couverture nulle" alors que R471 prouve des résolutions |
| `logs/R471_mapping_stats.json` | 16 corpus traités | La vérité des faits : 16 langues avec résolutions mesurées |
| `src/artcb/ir/concept_lexicon.py` | Docstring "14-language completion" | Sous-estimation après R430 |

**Conséquence :** toute déclaration "N langues supportées" depuis une constante locale ou un artefact historique était potentiellement fausse.

---

## 2. Fichiers créés

| Fichier | Rôle |
|---------|------|
| `rules/LANGUAGE_REGISTRY_CANONICAL.json` | **Source de vérité unique** — 16 langues avec état réel, résolutions R471, divergences documentées |
| `src/artcb/language/canonical_registry.py` | Module Python — `CanonicalLanguageRegistry`, `get_supported_isos()`, `get_language_state()`, `assert_registry_sha()`, `get_divergences()` |
| `tests/test_r485_canonical_registry.py` | 20 tests T01→T20 |
| `rapports/rapports/R485_canonical_language_registry_2026-09-26.md` | Ce rapport |

---

## 3. État réel des 16 langues (HEAD `63bde4c`)

### Résolutions R471 par langue

| ISO | Langue | Entrées R471 | Résolues | Taux | Divergence |
|-----|--------|-------------|----------|------|------------|
| tr | Turkish | 2 891 601 | 6 377 | 0.2205% | ⚠️ registry=NOT_STARTED |
| es | Spanish | 1 992 273 | 1 553 | 0.0780% | — |
| id | Indonesian | 79 949 | 61 | 0.0763% | ⚠️ registry=NOT_STARTED |
| ja | Japanese | 1 048 878 | 743 | 0.0708% | ⚠️ registry=NOT_STARTED |
| pt | Portuguese | 909 945 | 613 | 0.0674% | — |
| fr | French | 784 019 | 446 | 0.0569% | — |
| pl | Polish | 1 885 859 | 1 114 | 0.0591% | ⚠️ registry=NOT_STARTED |
| de | German | 1 733 696 | 791 | 0.0456% | ⚠️ registry=NOT_STARTED |
| ar | Arabic | 1 373 037 | 449 | 0.0327% | ⚠️ registry=NOT_STARTED |
| la | Latin | 2 042 686 | 516 | 0.0253% | ⚠️ absent du registre |
| en | English | 2 360 112 | 563 | 0.0239% | — |
| pt-BR | Portuguese (BR) | 145 744 | 30 | 0.0206% | — |
| ko | Korean | 463 834 | 84 | 0.0181% | ⚠️ registry=NOT_STARTED |
| ru | Russian | 1 935 993 | 286 | 0.0148% | — |
| zh | Chinese | 472 921 | 70 | 0.0148% | — |
| it | Italian | 1 363 559 | 83 | 0.0061% | — |

**Total R471 : 21 484 106 entrées — 13 779 résolues (0.064%) — closure_ok=True**

### 8 divergences confirmées

Les 8 langues suivantes ont `artcd_registry_status=NOT_STARTED` ou `NOT_IN_REGISTRY` alors que R471 a résolu des entrées non nulles :

```
ar   : registry=NOT_STARTED  mais R471 resolved=449
de   : registry=NOT_STARTED  mais R471 resolved=791
id   : registry=NOT_STARTED  mais R471 resolved=61
ja   : registry=NOT_STARTED  mais R471 resolved=743
ko   : registry=NOT_STARTED  mais R471 resolved=84
pl   : registry=NOT_STARTED  mais R471 resolved=1114
tr   : registry=NOT_STARTED  mais R471 resolved=6377
la   : absent du registre     mais R471 resolved=516
```

---

## 4. Avant / Après

### Avant — Déclaration dispersée (risque de faux résultat)

**`rules/artcd_language_registry.json`** (avant R485) :
```json
{"language_id": "LANG-AR", "status": "NOT_STARTED", "concept_lexicon_coverage": "none", ...}
```

**`logs/R471_mapping_stats.json`** :
```json
{"ar": {"resolved": 449, "r471_resolution_rate_pct": 0.0327}}
```
→ Contradiction non documentée.

**`ARTCB_14_LANGUAGES.json`** :
```json
{"total_languages": null, "fully_certified": null}
```
→ Structure inutilisable.

### Après — Source de vérité unique

**`rules/LANGUAGE_REGISTRY_CANONICAL.json`** (R485) :
```json
{
  "iso": "ar",
  "concept_lexicon_status": "PARTIAL",
  "r471_resolved": 449,
  "artcd_registry_status": "NOT_STARTED",
  "has_divergence": true,
  "divergence": "CONFIRMED: registry says NOT_STARTED but R471 resolved 449 entries"
}
```

**`src/artcb/language/canonical_registry.py`** :
```python
# Toute déclaration de couverture passe par :
reg = CanonicalLanguageRegistry()
state = reg.get_language_state("ar")  # concept_lexicon_status="PARTIAL", r471_resolved=449
sha = reg.get_language_registry_sha()  # SHA-256 du fichier = preuve d'audit
```

---

## 5. Résultats des tests

```
tests/test_r485_canonical_registry.py   20/20 PASS — 0.42s
+ gate DO-178C partiel :                81/81 PASS — 6.04s
```

Tests clés :
- T04 : exactement 16 langues chargées
- T05 : 16 ISO attendus (fr/en/es/pt/pt-BR/it/ru/zh/ar/de/id/ja/ko/pl/tr/la)
- T13 : exactement 8 divergences (AR/DE/ID/JA/KO/PL/TR/LA)
- T19 : somme résolus par langue == total summary (cohérence arithmétique)
- T11/T12 : `assert_registry_sha()` valide/invalide

---

## 6. Réponse à l'audit expert — État honnête SOL

| Couche SOL recommandée | État vérifié HEAD |
|------------------------|-------------------|
| Canonical Language Registry | ✅ **DONE_VERIFIED** (R485) |
| 16-language semantic equivalence benchmark | ❌ OPEN — test T30 "16 phrases → même ConceptGraph" absent |
| Forensic lineage par couche | ❌ PARTIAL — ForensicLedger existe, pas branché couche-par-couche |
| Monte Carlo candidats linguistiques | ❌ OPEN — simulation économique uniquement (R162) |
| Pareto frontier sémantique | ❌ OPEN — analyses dans rapports, pas en `src/` |
| Pareto inversé | ❌ OPEN |
| TSP / Semantic Routing | ❌ OPEN |

**Priorité suivante : R486 — Benchmark équivalence sémantique 16 langues** (le test ultime §30 de l'audit expert).

---

## 7. Limites et invariants

- `CERTIFIED_100 = false` — invariant absolu
- `unique_human_proven = False` — invariant absolu
- Taux de résolution 0.064% ≠ "16 langues couvertes" — couverture partielle honnêtement documentée
- `LANGUAGE_REGISTRY_SHA = e3241704c621889d...` — toute mesure de couverture doit enregistrer ce SHA
- `artcd_language_registry.json` et `ARTCB_14_LANGUAGES.json` restent présents pour compatibilité historique mais **ne sont plus la source de vérité**

---

*Rapport généré en mode DEBUG — CERTIFIED_100=false*
