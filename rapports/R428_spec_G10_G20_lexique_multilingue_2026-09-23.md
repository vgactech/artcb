# R428 — Spécification G10→G20 : Lexique Multilingue ARTCB + Language Registry + Canonical Vocabulary

**Date :** 2026-09-23  
**SHA HEAD :** `9bb72cd` (avant ce commit)  
**CERTIFIED_100 :** false  
**Mode :** DEBUG ACTIF  
**Avancement :** 100 % — rapport produit

---

## 0. Contexte

Ce rapport fait suite à l'audit expert reçu dans le prompt (SHA `9bb72cd`) qui identifiait 11 nouveaux gaps (G10→G20) liés à la bibliothèque linguistique multilingue ARTCB.

**Gaps adressés ce commit :**
- G5 — `artcd_canonical_vocabulary.json` — **BOOTSTRAP_DONE**
- G17 — `artcd_language_registry.json` — **BOOTSTRAP_DONE**
- G10→G16, G18→G20 — spécifiés formellement, **OPEN** (travaux futurs)

---

## 1. AVANT → APRÈS

### Fichier 1 : `rules/artcd_canonical_vocabulary.json`

**AVANT :** Inexistant (gap G5 identifié en R421).

**APRÈS :** Créé — 20 types sémantiques fondamentaux + 12 types d'arcs + 8 marqueurs épistémiques.

| Champ | Valeur |
|-------|--------|
| `semantic_types` | 20 types (ST-F, ST-E, ST-R, ST-H, ST-D, ST-G, ST-P, ST-C, ST-M, ST-AGT, ST-PROP, ST-ACT, ST-STATE, ST-REL, ST-ENT, ST-QUANT, ST-TIME, ST-LOC, ST-KNOW, ST-EXPR) |
| `edge_types` | 12 arcs (→, ⇒, ⊃, →t, ⊥, ⊢, ≡, ↔, isa, hpt, iof, sup) |
| `epistemic_markers` | 8 (TRUE, FALSE, UNKNOWN, INFERRED, OPINION, PROVEN, DISPUTED, PREDICTION) |
| Langues dans `labels` | 14 (fr, en, es, pt, it, ru, zh-hans, ar, de, id, ja, ko, pl, tr) |

**Cohérence avec le code existant :**
- Les types ST-F/E/R/H/D/G/P/C/M correspondent directement à `NodeType` dans [`src/artcb/ir/grammar.py`](src/artcb/ir/grammar.py:9)
- Les arcs →/⇒/⊃/→t/⊥/⊢/≡/↔ correspondent à `EdgeType` dans [`src/artcb/ir/grammar.py`](src/artcb/ir/grammar.py:22)

---

### Fichier 2 : `rules/artcd_language_registry.json`

**AVANT :** Inexistant (gap G17 — aucun registre officiel des 14 langues).

**APRÈS :** Créé — 14 langues officielles avec métadonnées complètes.

| Langue | ISO | Script | Direction | Statut lexique | UI i18n |
|--------|-----|--------|-----------|----------------|---------|
| French | fr | Latin | ltr | PARTIAL | ✅ DONE |
| English | en | Latin | ltr | PARTIAL | ✅ DONE |
| Spanish | es | Latin | ltr | PARTIAL | ✅ DONE |
| Portuguese | pt | Latin | ltr | PARTIAL | ✅ DONE |
| Italian | it | Latin | ltr | PARTIAL | ✅ DONE |
| Russian | ru | Cyrillic | ltr | PARTIAL | ✅ DONE |
| Chinese | zh | Han | ltr | PARTIAL | ✅ DONE |
| **Arabic** | ar | Arabic | **rtl** | NOT_STARTED | ❌ TODO |
| **German** | de | Latin | ltr | NOT_STARTED | ❌ TODO |
| **Indonesian** | id | Latin | ltr | NOT_STARTED | ❌ TODO |
| **Japanese** | ja | mixed | ltr | NOT_STARTED | ❌ TODO |
| **Korean** | ko | Hangul | ltr | NOT_STARTED | ❌ TODO |
| **Polish** | pl | Latin | ltr | NOT_STARTED | ❌ TODO |
| **Turkish** | tr | Latin | ltr | NOT_STARTED | ❌ TODO |

---

## 2. Spécification formelle G10→G20

### G10 — Multilingual Lexical Coverage

**Problème :** [`src/artcb/ir/concept_lexicon.py`](src/artcb/ir/concept_lexicon.py) couvre ~7 langues avec ~200 alias manuels. Les 7 nouvelles langues (ar, de, id, ja, ko, pl, tr) ont zéro entrée.

**Définition mesurable :**
```
Coverage(lang) = lexèmes_ARTCB_reconnus / lexèmes_corpus_référence_sélectionné
```

**Corpus de référence recommandé :** Wikidata Lexeme dump filtré par langue (licence CC0).

**Livrable attendu :** `src/artcb/ir/lexicon_<lang>.py` pour chaque langue, ou extension du `concept_lexicon.py` avec namespace par langue.

---

### G11 — Morphological Coverage

**Problème :** L'encodeur actuel fait un matching sur des tokens bruts. Pour les langues flexionnelles (RU, PL, DE, AR, TR), les formes fléchies ne matchent pas le lemme.

**Exemple :**
```
FR : "voiture", "voitures"  → code C2  (partiellement couvert)
RU : "автомобиль", "автомобиля", "автомобилей"  → C2 (zéro couverture)
```

**Livrable attendu :** `src/artcb/ir/morphology/` — lemmatiseur léger par langue, ou intégration d'une bibliothèque de lemmatisation (spaCy lemmatizer, pour les langues qui en ont besoin).

**Contrainte :** Pas d'ajout de dépendance lourde sur les nœuds live sans test préalable (L-048).

---

### G12 — Sense / Polysemy Resolution

**Problème :** Le lexique actuel assigne `C2 = vehicle` pour "voiture" sans gérer les homonymes. Ex : "car" en anglais = vehicle, mais aussi conjonction ("because" en FR archaïque).

**Livrable attendu :** `src/artcb/ir/sense_resolver.py` — résolution de sens par contexte (sac de mots voisins + type de NodeType attendu).

---

### G13 — Expression Coverage (idiomes, phrasèmes)

**Problème :** L'encodeur traite les phrases token par token. Les expressions figées comme "prendre en compte", "take into account", "tener en cuenta" ne sont pas reconnues comme une unité sémantique.

**Livrable attendu :** `src/artcb/ir/expression_lexicon.py` — table d'expressions multi-tokens → ExpressionID.

---

### G14 — Named Entity Layer

**Problème :** ARTCB ne distingue pas "Paris (ville)" de "Paris (prénom)". Les entités nommées (organisations, technologies, personnes) ne sont pas indexées séparément.

**Livrable attendu :** `src/artcb/ir/entity_registry.py` + `rules/artcd_entity_index.json` (bootstrap minimal : blockchain keywords, crypto terms, ARTCB project entities).

---

### G15 — Provenance / License / Source Versioning

**Problème :** Les alias actuels dans `concept_lexicon.py` sont main-crafted sans traçabilité de source, sans licence, sans version.

**Livrable attendu :** Chaque entrée du lexique doit avoir :
```json
{
  "source": "hand-crafted | wikidata | wiktionary | custom",
  "source_version": "2026-09",
  "license": "CC0 | CC-BY-SA-4.0 | ARTCB-proprietary",
  "source_id": "optional external id",
  "added_by": "R321 | R428 | ...",
  "added_at": "ISO timestamp"
}
```

---

### G16 — Cross-language Concept Equivalence Test Suite

**Problème :** Il n'existe pas de test qui vérifie que "voiture" (FR) → ConceptID → "car" (EN) → même ConceptID.

**Livrable attendu :** `tests/test_r428_cross_language_equivalence.py` — test que les aliases FR/EN/ES/PT/IT/RU/ZH de mêmes concepts convergent vers le même ARTCB code.

---

### G17 — Language Registry ✅ BOOTSTRAP_DONE

**Livrable :** `rules/artcd_language_registry.json` — 14 langues, métadonnées morphologiques, statuts.

---

### G18 — Coverage Benchmark 14 Languages

**Problème :** Il n'existe pas de métrique de couverture par langue.

**Livrable attendu :** `scripts/artcb_r428_coverage_benchmark.py` — mesure pour chaque langue :
- nombre de lexèmes reconnus sur un corpus de référence
- nombre de formes morphologiques couvertes
- nombre d'expressions couvertes
- taux de convergence ConceptID cross-langue

**Critère de succès :** Rapport de couverture reproductible.

---

### G19 — Contradiction / Knowledge Provenance Engine

**Problème :** Si deux sources disent `X=Y` et `X≠Y`, ARTCB n'a pas de mécanisme pour les conserver séparément avec leurs provenances.

**Livrable attendu :** Extension de `concept.py` avec `KnowledgeProvenance` et relation `ET-CONTRADICTS` (déjà dans `grammar.py` via `EdgeType.CONTRADICTS`).

---

### G20 — Lexicon / Ontology / Knowledge Separation

**Problème :** Actuellement tout est mélangé dans `concept_lexicon.py`. Il manque la séparation architecturale :

```
LEXICON        → mots, formes, sens
ONTOLOGY       → concepts, relations, hiérarchies
KNOWLEDGE BASE → faits, événements, sources, preuves
```

**Livrable attendu :** Architecture `src/artcb/ir/` réorganisée :
```
src/artcb/ir/
  lexicon/          ← G10-G13 (lemmes, formes, sens, expressions)
  ontology/         ← G5 (types canoniques, relations, hiérarchies)
  knowledge/        ← G14, G19 (entités, faits, provenances)
  reasoning.py      ← G4 (moteur déduction natif)
```

---

## 3. Distinction importante : 100% scope ≠ CERTIFIED_100

Conformément à l'audit expert (SHA `9bb72cd`) :

| Compteur | R428 |
|----------|------|
| `SCOPE_COMPLETION` (R428) | 100 % |
| `PROJECT_COMPLETION` | non certifié |
| `CERTIFIED_100` | **false** |

G5 et G17 sont en BOOTSTRAP_DONE. Les 9 autres gaps (G10-G16, G18-G20) restent OPEN.

---

## 4. Fichiers produits ce commit

| Fichier | Action |
|---------|--------|
| `rules/artcd_canonical_vocabulary.json` | CRÉÉ — 20 types sémantiques, 12 arcs, 8 marqueurs épistémiques, 14 langues |
| `rules/artcd_language_registry.json` | CRÉÉ — 14 langues officielles, métadonnées morphologiques, statuts |
| `rapports/R428_spec_G10_G20_lexique_multilingue_2026-09-23.md` | CRÉÉ — spécification formelle |

---

## 5. Prochaines actions recommandées (ordre de priorité)

| Priorité | Chantier | Gap |
|----------|----------|-----|
| P0 | FHE `check_uniqueness()` | TASK-001 |
| P0 | `src/artcb/ir/reasoning.py` moteur déduction | G4 |
| P1 | Cross-language equivalence tests | G16 |
| P1 | Sense resolver basic | G12 |
| P2 | Morphological coverage FR/EN/ES | G11 |
| P2 | Coverage benchmark script | G18 |
| P3 | 7 nouvelles langues UI i18n | G10/R422 |
| P3 | Named entity bootstrap | G14 |
