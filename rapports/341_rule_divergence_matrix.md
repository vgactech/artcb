# R341 — Matrice de divergence RULE → SOURCE → CODE → TEST → LIVE → STATUS

**UTC:** 2026-09-14T09:05:00Z  
**CERTIFIED_100:** false  
**SHA live référence (dns_fix):** `d8e67cd…` ×4 = `origin/main` (mesuré avant push de ce rapport)

## Accord avec l’audit opérateur

- Nouvelles règles R337→R340 : **oui** (télémétrie, capability-first, H0–H4, binding, corpus map, INVALID_NO_SAMPLE).
- Toutes les anciennes règles respectées / fermées : **non**.
- `registered_rules` ≠ corpus ; couverture **PARTIAL**.
- Tokenomics / PoL / V-01…V-07 / biométrie : **pas** auto-certifiés.

## Pipeline à 6 niveaux (jamais collapsé)

```text
DECIDED → REGISTERED → CODED → TESTED → LIVE_MEASURED → CERTIFIED
```

Plus buckets : `SIMULATED_ONLY`, `OPEN`, `NOT_PROVEN`, `PARTIAL`.

## Résumé matrice (registry)

| status_max | count (approx) |
|---|---:|
| LIVE_MEASURED | 11+ |
| TESTED | 1 |
| CODED | 2 |
| REGISTERED | 4 |
| CERTIFIED | **0** |
| open_flagged | ≥6 |

Artefact : `rules/rule_divergence_matrix.json`

## Buckets hors registry (exemples)

| bucket | kind | status_max |
|---|---|---|
| UB-TOKENOMICS-R-H | INVARIANT | SIMULATED_ONLY |
| UB-POL-TARGET | SPEC | SIMULATED_ONLY |
| UB-V01-V07 | CHECK | OPEN |
| UB-HUMAN-BIOMETRIC | SPEC | DECIDED |
| UB-ISSUE-86-ACL | CHECK | NOT_PROVEN |
| UB-CONSENSUS-PBFT | INVARIANT | PARTIAL |
| UB-PROTOCOLE-17 | RULE | DECIDED |

## Ouverts (non abandonnés)

#77 N04/C04 · #86 ACL · Anti-Sybil ≥50 · H2/FIDO · NodeCertificate CA · lineage ligne-à-ligne du corpus ~175 · V-01…V-07 · #87

## Remesures parallèles (ce tour)

| Item | Verdict |
|---|---|
| SHA live ×4 | `d8e67cd…` = origin/main |
| Anti-Sybil | sample_count=**6** ; quantity_gate_50=false ; campaign_certified=false |
| #86 r331 | remesure lancée en parallèle — voir `logs/R341/r331.json` (si vide: encore NOT_PROVEN historique) |

Jamais wipe. Jamais `18/18` = couverture corpus.

