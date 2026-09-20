# R381 — Correction status CR-* DETECTED_NOT_CLASSIFIED → status réel

**Date :** 2026-09-19  
**Session :** Bob IDE — suite `continue`  
**HEAD avant :** 6bc9fba  
**CERTIFIED_100 :** false  
**Mode DEBUG :** actif

---

## Problème corrigé

Toutes les 230 entrées de `rules/rule_corpus_index.json` portaient `status="DETECTED_NOT_CLASSIFIED"` bien que le champ `primary_domain` soit déjà classifié par `artcb_r393_v2`. Le status n'avait jamais été mis à jour après la classification initiale.

---

## AVANT → APRÈS

**Fichier :** `rules/rule_corpus_index.json`  
**Lignes concernées :** `"status"` de chacune des 230 entrées CR-*

| Status AVANT | Status APRÈS | Nombre |
|-------------|--------------|--------|
| `DETECTED_NOT_CLASSIFIED` | `DETECTED_UNREGISTERED` (RULE sans rt_rule_id) | 113 |
| `DETECTED_NOT_CLASSIFIED` | `DECISION_ACTIVE` (kind=DECISION) | 47 |
| `DETECTED_NOT_CLASSIFIED` | `LESSON_DOCUMENTED` (kind=LESSON) | 44 |
| `DETECTED_NOT_CLASSIFIED` | `REGISTERED_IN_REGISTRY` (RULE avec rt_rule_id) | 20 |
| `DETECTED_NOT_CLASSIFIED` | `SPEC_DOCUMENTED` (kind=SPEC) | 2 |
| `DETECTED_NOT_CLASSIFIED` | `CHECK_DOCUMENTED` | 1 |
| `DETECTED_NOT_CLASSIFIED` | `CONVENTION_DOCUMENTED` | 1 |
| `DETECTED_NOT_CLASSIFIED` | `EVIDENCE_DOCUMENTED` | 1 |
| `DETECTED_NOT_CLASSIFIED` | `QUESTION_OPEN` | 1 |
| **TOTAL** | | **230 → 0 DETECTED_NOT_CLASSIFIED** |

---

## Logique de classification (script `scripts/artcb_r381_corpus_status_update.py`)

```
RULE  + rt_rule_id non nul  →  REGISTERED_IN_REGISTRY
RULE  + rt_rule_id nul      →  DETECTED_UNREGISTERED
DECISION                    →  DECISION_ACTIVE
LESSON                      →  LESSON_DOCUMENTED
SPEC                        →  SPEC_DOCUMENTED
CHECK                       →  CHECK_DOCUMENTED
CONVENTION                  →  CONVENTION_DOCUMENTED
EVIDENCE                    →  EVIDENCE_DOCUMENTED
QUESTION                    →  QUESTION_OPEN
```

**Conditions :** `primary_domain` doit être non nul (déjà classifié) + status ne doit pas être dans `STATUS_IMMUTABLE` (VALIDATED/CERTIFIED/DEPRECATED/SUPERSEDED/CONFLICT).

---

## Observation importante : 113 DETECTED_UNREGISTERED

113 règles R-* sont détectées dans le corpus mais **ne correspondent à aucun RT-* dans le registre**. Ce sont des règles documentées dans les rapports/sessions sans jamais avoir été formalisées en règle opérationnelle.

Ce n'est pas un bug — c'est l'état réel du corpus. Ces règles sont candidates à être enregistrées dans `rule_registry.json` (RT-* suivants).

---

## Fichiers produits

| Fichier | Action |
|---------|--------|
| `rules/rule_corpus_index.json` | **230 entrées mises à jour** (champs `status`, `status_updated_by`, `status_updated_ts`) |
| `rules/rule_corpus_index.json.bak_r381` | Backup avant modification |
| `scripts/artcb_r381_corpus_status_update.py` | Script de mise à jour (MODULE_VERSION 1.0.0) |

---

## Résultat de l'exécution (logs DEBUG complets disponibles)

```
Entrées totales  : 230
Mises à jour     : 230
Inchangées       : 0
DETECTED_NOT_CLASSIFIED restants : 0

Répartition finale :
  DETECTED_UNREGISTERED               : 113
  DECISION_ACTIVE                     : 47
  LESSON_DOCUMENTED                   : 44
  REGISTERED_IN_REGISTRY              : 20
  SPEC_DOCUMENTED                     : 2
  CHECK_DOCUMENTED                    : 1
  CONVENTION_DOCUMENTED               : 1
  EVIDENCE_DOCUMENTED                 : 1
  QUESTION_OPEN                       : 1
```

---

## Ce qui RESTE à faire sur les rules

1. **Enregistrer les 113 DETECTED_UNREGISTERED pertinentes** en RT-* dans `rule_registry.json`
2. **Sous-domaines** : affiner PROTOCOL (96) → CRYPTO / BIOMETRIC / CONSENSUS / ECONOMICS
3. **Réorganisation automatique** par domaine/sous-domaine (script dédié)

---

*Rapport généré : 2026-09-19 | CERTIFIED_100=false | MODE DEBUG actif*
