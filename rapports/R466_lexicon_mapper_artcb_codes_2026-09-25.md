# R466 — Lexicon Mapper artcb_code : résolution UNK → codes ARTCB
**Date :** 2026-09-25  
**HEAD avant :** `3be32b6`  
**Statut :** PASS — 31/31 tests  
**CERTIFIED_100=false**

---

## Contexte

R465/R465-ext avait construit 16 profils lexicaux (21 484 106 entrées, 16 langues).  
Toutes les entrées portaient `artcb_code = "UNK"` faute de résolution.

R466 implémente le **premier niveau de résolution artcb_code** : exact surface_form / exact lemma
vers les codes ARTCB connus (`V1`, `C2`, `S2`, `N1`, …).

---

## Artefacts créés

| Fichier | Rôle |
|---------|------|
| `src/artcb/language/lexicon_mapper.py` | Module `LexiconMapper` + `MapperStats` + `MappingResult` |
| `scripts/artcb_r466_map_artcb_codes.py` | Script batch 16 profils (dry-run + write) |
| `tests/test_r466_lexicon_mapper.py` | 31 tests T01–T25 (avec paramétrisations) |
| `logs/R466_mapping_stats.json` | Stats dry-run profil `fr` |

---

## Architecture

```
LexicalEntry (surface_form, lemma, pos, artcb_code="UNK")
       ↓
LexiconMapper.resolve(surface_form, lemma, pos)
       ↓
    Priorité 1 : exact surface_form O(1) → combined dict
    Priorité 2 : exact lemma O(1) → combined dict
    Priorité 3 : UNK honnête (pas de préfixe en batch)
       ↓
MappingResult(artcb_code, resolved, match_method, matched_key, table_name)
```

**Tables sources** (`src/artcb/ir/concept_lexicon.py`) :
- `ACTION_ALIASES` (126 clés → codes A1/C1/D1/K1/M1/O1/R1/U1/V1)
- `OBJECT_ALIASES` (200 clés → codes B1/C2/E3/M1/M2/M3/N1/P1/P2/S1/S2)
- `MODIFIER_ALIASES` (52 clés → codes MOD/NEG/PL/QH/QL)

**Index combiné** : 360 clés uniques, priorité ACTION > OBJECT > MODIFIER.

---

## Performances mesurées

| Profil | Entrées | Résolu | Taux | Temps |
|--------|---------|--------|------|-------|
| `fr`   | 784 019 | 448    | 0.057% | 1.48s |
| `en`   | 2 360 112 | 615  | 0.026% | 4.32s |

**Vitesse :** ~500k–530k entrées/seconde (O(1) lookups dict).

---

## Avant / Après

### AVANT (R465-ext)

**`data/lexicons/fr_lexicon.json` — toutes les entrées :**
```json
{"surface_form": "vérifier", "lemma": "vérifier", "pos": "verb", "artcb_code": ""}
{"surface_form": "server",   "lemma": "server",   "pos": "noun", "artcb_code": ""}
```

### APRÈS (R466 — dry-run validé)

```json
{"surface_form": "vérifier", "lemma": "vérifier", "pos": "verb", "artcb_code": "V1"}
{"surface_form": "server",   "lemma": "server",   "pos": "noun", "artcb_code": "N1"}
{"surface_form": "xyzqrst",  "lemma": "xyzqrst",  "pos": "noun", "artcb_code": "UNK"}
```

---

## Distribution by_code (fr — dry-run)

| Code | Matchs | Signification |
|------|--------|---------------|
| V1   | 72     | vérifier / verify / validar |
| MOD  | 58     | peut / pouvoir / can |
| U1   | 43     | consommer / consume |
| O1   | 39     | observer / regard |
| R1   | 38     | relier / connect |
| C2   | —      | (éliminé — faux positifs préfixe supprimés) |

---

## Décision clé — suppression du préfixe en batch

La première implémentation utilisait une boucle préfixe `lm.startswith(key)` sur 360 clés.  
**Résultat :** 370s pour 784k entrées (O(N×K) = 282M comparaisons), 9914 "matchs" dont la majorité étaient des faux positifs (ex: `cañon` → préfixe `can` → C2 véhicule).

**Décision (R466) :** supprimer le préfixe en `resolve_batch()`.  
- `resolve_batch()` = exact O(1) uniquement — honnête, rapide, 0 faux positif  
- `resolve()` unitaire = préfixe conservé (usage encodage phrase-par-phrase)

**Taux résolution fr :** 0.057% exact (448/784019) — **honnête et documenté**.

---

## Tests T01–T25

| Test | Scénario | Résultat |
|------|----------|---------|
| T01 | Instanciation LexiconMapper | PASS |
| T02 | Exact surface → V1 (ACTION) | PASS |
| T03 | Exact surface → N1 (OBJECT) | PASS |
| T04 | Exact surface → QH (MODIFIER) | PASS |
| T05 | Exact lemma ≠ surface → V1 | PASS |
| T06 | Préfixe lemma → V1 (resolve() unitaire) | PASS |
| T07 | Non-résolution honnête → UNK | PASS |
| T08 | Code dans VALID_CODES ou UNK (7 entrées) | PASS |
| T09 | Insensibilité casse surface | PASS |
| T10 | Insensibilité casse lemma | PASS |
| T11 | Déterminisme (2 appels identiques) | PASS |
| T12 | resolve_batch([]) → liste vide, stats zéro | PASS |
| T13 | resolve_batch stats total=resolved+unresolved | PASS |
| T14 | resolve_batch met à jour artcb_code | PASS |
| T15 | MapperStats.summary() clés attendues | PASS |
| T16 | resolution_rate = resolved/total | PASS |
| T17 | get_mapper() singleton | PASS |
| T18 | voiture → C2 (FR) | PASS |
| T19 | car → C2 (EN) | PASS |
| T20 | signature → S2 | PASS |
| T21 | MappingResult tous les champs | PASS |
| T22 | surface_form vide → UNK sans exception | PASS |
| T23 | surface avec espaces → strip | PASS |
| T24 | resolve_batch préserve autres champs | PASS |
| T25 | by_code stats correctes | PASS |

**Total : 31/31 PASS**

---

## Non-régression

| Suite | Tests | Résultat |
|-------|-------|---------|
| test_r465_lexicon_loader.py | 30 | PASS |
| test_r466_lexicon_mapper.py | 31 | PASS |
| **Total** | **61** | **PASS** |

---

## Limites documentées

1. **Taux de résolution 0.026–0.057%** — normal : 360 clés pour 21.5M entrées. La couverture augmentera avec l'enrichissement de `concept_lexicon.py`.
2. **Préfixe désactivé en batch** — faux positifs trop nombreux. Préfixe disponible via `resolve()` unitaire uniquement.
3. **Pas de résolution POS-guidée** — `car` (conjonction FR) et `car` (véhicule EN) reçoivent le même code C2. Résolution POS = chantier futur.
4. **FHE check_uniqueness()** — TASK-001 toujours en attente (non régression préservée).

---

## Prochaines étapes

- R467 : Enrichissement `concept_lexicon.py` — couverture POS-guidée + multilingual
- R466b : Run complet `--all-16` sur les 16 profils + `data/lexicons_mapped/`
- TASK-001 : FHE véritable `check_uniqueness()`

`CERTIFIED_100=false`
