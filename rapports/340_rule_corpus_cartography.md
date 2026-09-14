# R340 — Rule corpus cartography + measure validity

**UTC:** 2026-09-14T07:55:00Z  
**CERTIFIED_100:** false

## Verdict

`registry_v: 4` = version du fichier `rules/rule_registry.json`.  
`registered_rules: 18` (ex-affichage `rules_total: 16` puis +2) = **entrées télémétrie seulement**, pas le corpus ARTCB.

Corpus détecté (marqueurs numérotés, **pas** règles sémantiques uniques) : **~174**.  
`unmapped_estimate` élevé → couverture registry **PARTIAL**.

## Corrections appliquées

1. Badge hook : `registered_rules` + `corpus_markers_sum` / `unmapped_estimate` ; note « ≠ corpus ».
2. Fichiers : `rules/rule_sources.json`, `rule_lineage.json`, `rule_conflicts.json`, `rule_coverage.json`.
3. Sync `.cursor/rules/artcb-live-node.mdc` : append **R339** + **R340**.
4. Long poll DNS poison → `logs/R340/dns_poison_long_poll_INVALID_NO_SAMPLE.json` (`INVALID_NO_SAMPLE`).
5. Règles registry : `RT-CORPUS-MAP`, `RT-MEASURE-VALID` → **registry_v 4**.

## SHA live (référence)

| Endpoint | `/health.git_sha` |
|---|---|
| artcb.me | `d4afd603bfafc520b08260787c5b766731cae31f` |
| n2 | idem |
| n3 | idem |
| n4 | idem |
| origin/main | idem |

→ campagne certifiable sur **SHA exécuté** = `d4afd60…` ×4 (avec `artcb_dns_fix`).

## Ouverts (non abandonnés)

#77 N04/C04 · #86 ACL · Anti-Sybil ≥50 · H2/FIDO · CA on-chain · tokenomics/consensus invariants hors registry · lineage détaillée RuleID↔ligne · #87 · langage · V-01…V-07

Jamais wipe. Jamais `rules_total` = couverture globale.
