# R427 — Rule Telemetry : Reclassification par domaine

**Date :** 2026-09-23  
**SHA HEAD :** `de1d6bd`  
**Mode :** DEBUG ACTIF  
**dry_run :** False  
**CERTIFIED_100 :** false

---

## Résumé

| Métrique | Valeur |
|----------|--------|
| Total entrées | 230 |
| Modifications | 21 |
| Conservées | 209 |

---

## AVANT — Distribution par domaine

| Domaine | Count |
|---------|-------|
| GOVERNANCE | 48 |
| IDENTITY | 1 |
| LESSONS | 44 |
| NETWORK | 39 |
| PROTOCOL | 96 |
| ROADMAP | 1 |
| TESTING | 1 |

---

## APRÈS — Distribution par domaine

| Domaine | Count |
|---------|-------|
| GOVERNANCE | 48 |
| IDENTITY | 1 |
| LESSONS | 46 |
| NETWORK | 39 |
| PROTOCOL | 76 |
| PROTOCOL_CHAIN | 18 |
| ROADMAP | 2 |

---

## Échantillon des modifications (30 premières)

| corpus_id | ref | kind | Avant | Après |
|-----------|-----|------|-------|-------|
| CR-EVI-TASK-LEDGER-cfb78159 | TASK_LEDGER | EVIDENCE | TESTING | PROTOCOL_CHAIN |
| CR-RUL-R355-fe658d5a | R355 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R356-26ba3a15 | R356 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R357-aea1964f | R357 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R358-bb825dfa | R358 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R359-f39bd514 | R359 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R360-6003b0da | R360 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R361-6a6a1c77 | R361 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R362-46f35959 | R362 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R363B-cdf7a2bd | R363b | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R363C-15ee5e5c | R363c | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R364-be130080 | R364 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R365-8da1d8d1 | R365 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R366-b3e9a651 | R366 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R367-29a72d19 | R367 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R368-9c011044 | R368 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R369-7b39d400 | R369 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-R370-9ef02775 | R370 | RULE | PROTOCOL | PROTOCOL_CHAIN |
| CR-RUL-RT-DIVERGENCE-341-4e6e99fe | RT-DIVERGENCE-341 | RULE | PROTOCOL | LESSONS |
| CR-RUL-RT-SYBIL-076-ff2f74b8 | RT-SYBIL-076 | RULE | PROTOCOL | LESSONS |
| CR-SPE-ROADMAP-89910cf9 | ROADMAP | SPEC | PROTOCOL | ROADMAP |

---

## Fichiers modifiés

| Fichier | Action |
|---------|--------|
| `rules/rule_corpus_index.json` | Reclassifié (backup `.bak_r427`) |
| `logs/R427_reclassify_result.json` | Log complet des modifications |

---

## Limites

- Classification basée sur mots-clés (heuristique) — pas de ML
- Domaines qui se chevauchent (ex: GOVERNANCE ↔ PROTOCOL_CHAIN) = premier match gagne
- `CERTIFIED_100=false` — validation manuelle recommandée sur les 30 changements ci-dessus