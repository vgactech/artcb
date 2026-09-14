# R344 — Audit conformité corpus R337/R340/R341

**UTC:** 2026-09-14T17:05:00Z  
**SHA local/HEAD:** `e302532…` (= origin/main au moment de l’audit)  
**CERTIFIED_100:** false  
**Verdict global:** **PARTIAL**

Artefact machine: `logs/R344/compliance_audit.json`

---

## Question obligatoire

> Le corpus normatif complet d'ARTCB est-il réellement transmis à l'agent, réellement utilisé, réellement vérifié et réellement prouvé ?

### **PARTIAL**

| Étape | Réponse | Preuve / limite |
|---|---|---|
| 1 Découvert | PARTIAL | sources listées dans `artcb_r340_rule_corpus_audit.py` ; pas tout le repo |
| 2 Extrait | PARTIAL | marqueurs numérotés regex |
| 3 Normalisé | PARTIAL | pas de semantic_hash unique |
| 4 Dédoublonné | **NO** | markers ≠ règles uniques |
| 5 Classifié | PARTIAL | catégories déclarées, pas appliquées ligne à ligne |
| 6 Enregistré registry | PARTIAL | **19** RT-* actives (v5) |
| 7 rule_coverage | PARTIAL | `mapped_to_source=PARTIAL`, unmapped≈158 |
| 8 Transmis runtime | PARTIAL | registry + badge oui ; corpus complet **non** comme RT-IDs |
| 9 Guide décisions | PARTIAL | Cursor `.mdc` / AUTO_PROMPT = texte ; télémétrie = display |
| 10 rule_usage | PARTIAL | jsonl local mesuré |
| 11 Preuve ≠ thinking | PARTIAL | garde `applied_confirmed` + `CONFIRMED_EVIDENCE` |
| 12 Pipeline R341 | PARTIAL | matrice présente ; `certified=0` |

---

## 1. Intégration : oui le mécanisme existe

Présent sur `main` :

- `rules/rule_registry.json` (v5, **19** règles dont `RT-CORPUS-MAP`, `RT-TELEMETRY`, `RT-DIVERGENCE-341`)
- `rules/rule_coverage.json`
- `src/artcb/rules/telemetry.py`
- hook `after_agent_thought.py` (RULE COMPLIANCE LIVE)
- `rules/rule_divergence_matrix.json` (R341)
- tests R337/R340/R341

**« Envoyé » ≠ corpus complet intégré.** C’est exactement ce que `RT-CORPUS-MAP` interdit de confondre.

---

## 2. Recalcul UI vs fichiers (Phase 9) — divergence réelle

| Source | registry_v (coverage) | registered_rules | markers | unmapped |
|---|---:|---:|---:|---:|
| `origin/main` **`rules/rule_registry.json`** | (champ registry) **5** | **19** | — | — |
| `origin/main` **`rules/rule_coverage.json`** | **4 (STALE)** | **18** | **175** | **157** |
| Badge / worktree (mesuré ce tour) | 5 | 19 | 177→181 | 158→162 |

**Ton intuition GitHub était correcte.** Sur `main` commit `e302532` :

- le **registry** a déjà **19** règles (v5) ;
- le fichier **`rule_coverage.json` versionné est en retard** (encore 18/175/157, `version: 4`) ;
- le badge lit la coverage **locale** (souvent régénérée) → 19/177+/158+ ;
- donc **affichage ≠ artefact GitHub**, sans que ce soit « inventé » : c’est un **fichier coverage non resynchronisé** après bump registry.

Marqueurs ≠ règles sémantiques uniques. La croissance 175→181 suit surtout l’ajout de texte dans AUTO_PROMPT / `.cursor/rules` (ex. R343), pas 6 nouvelles RT-*.

---

## 3. Runtime (Phase 4) — réponses explicites

| Q | Réponse |
|---|---|
| A. Lit le registry ? | **OUI** (`load_registry` → `summarize` → `badge_snapshot`) |
| B. Lit le corpus complet ? | **NON** (seulement `rule_coverage.json` pour markers/unmapped) |
| C. Seulement règles enregistrées pour usage ? | **OUI** pour `rule_usage.jsonl` (RT-IDs) |
| D. Non-mappé influence l’agent ? | **Pas via télémétrie** ; oui potentiellement via texte Cursor/AUTO_PROMPT rechargé |
| E. Risque de ne suivre que 19 règles ? | **OUI pour la couche télémétrie** ; le corpus texte reste parallèle et non instrumenté |

---

## 4. `applied=0` / `applied_confirmed=12` (Phase 5)

**Ce n’est pas une corruption des compteurs.**

Dans le code actuel, `applied` et `applied_confirmed` sont des **kinds d’événements indépendants** :

- `applied_confirmed` exige `evidence_kind ∈ CONFIRMED_EVIDENCE` + `evidence_ref`
- **n’exige pas** un événement `applied` préalable

Donc `applied_confirmed > applied` est **autorisé par design** — mais **sémantiquement trompeur** dans l’UI.

Mesure live locale :

```text
seen=11  checked=7  applied=0  applied_confirmed=12  violated=0  corrected=0  not_proven=10
```

**Ce que ça prouve :** des preuves indépendantes ont été journalisées.  
**Ce que ça ne prouve pas :** qu’une étape « applied » a existé, ni que 100 % du corpus est respecté.

### Correction proposée (après diagnostic)

1. Documenter clairement dans le badge : `applied_confirmed` = preuve indépendante, pas « applied+1 ».  
2. Option A : auto-émettre `applied` quand on confirme.  
3. Option B : renommer en `evidence_confirmed`.  

→ Implémentation minimale retenue : **clarifier le badge + test de sémantique** (pas de fake certified).

---

## 5. Thinking ≠ preuve (Phase 6)

Confirmé dans `append_event` :

- `applied_confirmed` refuse `agent_claim_only`
- refuse evidence_kind hors allowlist

---

## 6. Certification

`CERTIFIED_100` **doit rester false** tant que :

- déduplication sémantique absente  
- unmapped_estimate élevé  
- runtime n’enforce pas le corpus hors registry  
- R341 `certified=0`

---

## 7. Corrections recommandées (priorisées)

| ID | Action | Urgence |
|---|---|---|
| FIX-COUNTER-SEMANTICS | Clarifier badge / test | haute (lisibilité) |
| FIX-DEDUPE-SEMANTIC | hash sémantique avant unmapped | haute (honnêteté corpus) |
| FIX-REFRESH-COVERAGE | regen coverage à chaque bump registry | moyenne |
| FIX-RUNTIME-BRIDGE | lier alwaysApply sections → RT-IDs | longue |

**Ne pas** « réintégrer le corpus » comme s’il n’existait pas.
