# PBFT ARTCB — référence (265 + 266)

N=4 F=1 Q=3. Replica set = `OFFICIAL_COMPUTE_NODE_IDS`.
Primary = `OFFICIAL_COMPUTE_NODE_IDS[view % 4]`.

## Chemin réel

`construct (append dry_run)` → PRE-PREPARE (primary) → PREPARE Q=3 → COMMIT Q=3
→ certificat → `write_certified_block` / `import_extending_block`.

Un index avec certificat **ne peut pas** être remplacé (longest-chain refusée :
`pbft_finalized_conflict`).

## Exclusivité (266)

Sur un replica officiel, `append_block(visibility=public)` ne grave plus le jsonl
directement. Il construit, coordonne PBFT, puis `write_certified_block`.
`POST /ai/memo` public emprunte ce chemin. Les append **privés** restent locaux.
Import public avec `index >= 1087` exige un `pbft_cert` valide
(`pbft_cert_required` sinon). L'historique 0–1086 n'est pas réécrit.

`POST /pbft/client-request` : un non-primary soumet un bloc construit ; seul le
primary de la vue courante émet PRE-PREPARE (le bloc doit étendre le tip).

Deux PRE-PREPARE **valides** (même view, même seq, signatures primary, digests
≠) : un replica n'accepte pas le second (`equivocation`). Un split 2-2 ne
produit pas de certificat. Un second certificat pour le même seq est
`certificate_conflict`.

## View-change

R264 = baseline settlement (vue partagée). 265 VIEW-CHANGE transporte le P-set
(préparé). NEW-VIEW doit re-proposer le digest préparé le plus haut.

## Traces

Nanoseconde obligatoire : `ts_ns`, `dur_ns`, `data/trace/ns.jsonl`, kinds `pbft_*`.
Moins que ns = `NOT_VALIDATED`.

## Ce que R264 n'est pas

R264 n'est **pas** `PBFT_LIVE_E2E_PASS`. C'est la vue + VIEW-CHANGE/NEW-VIEW
settlement. La finalité des blocs est 265. L'exclusivité + Byzantine valide +
crash/partition sont 266 / T-E54.
