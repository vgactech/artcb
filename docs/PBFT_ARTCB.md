# PBFT ARTCB — référence (265)

N=4 F=1 Q=3. Replica set = `OFFICIAL_COMPUTE_NODE_IDS`.
Primary = `OFFICIAL_COMPUTE_NODE_IDS[view % 4]`.

## Chemin réel

`construct (append dry_run)` → PRE-PREPARE (primary) → PREPARE Q=3 → COMMIT Q=3
→ certificat → `write_certified_block` / `import_extending_block`.

Un index avec certificat **ne peut pas** être remplacé (longest-chain refusée :
`pbft_finalized_conflict`).

## View-change

R264 = baseline settlement (vue partagée). 265 VIEW-CHANGE transporte le P-set
(préparé). NEW-VIEW doit re-proposer le digest préparé le plus haut.

## Traces

Nanoseconde obligatoire : `ts_ns`, `dur_ns`, `data/trace/ns.jsonl`, kinds `pbft_*`.
Moins que ns = `NOT_VALIDATED`.

## Ce que R264 n'est pas

R264 n'est **pas** `PBFT_LIVE_E2E_PASS`. C'est la vue + VIEW-CHANGE/NEW-VIEW
settlement. La finalité des blocs est 265.
