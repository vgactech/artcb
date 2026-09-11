# R325 — parallel axes (R325_20260912T015048Z_4a64254a09a8)

`commit_sha` = `4a64254a09a85471a7a5ca052539f02dd3679ddc` (docs/branch HEAD)
`code_fix_attributed` = `f739a6b` (R324 fix for result attribution)

`CERTIFIED_100=false`

## A — Runtime alignment

- verdict: **PARTIAL_OR_DIVERGE**
- shas: `['4a64254a09a8']`
- heights: `['1141', '1832']`

## B — Publisher-death hard (hop=1 local)

- B n2/n3/n4 local: **True**
- cold empty: **True**
- publisher process stopped: **False**
- resilience measured: **True**

## C — Continuity 716

- verdict: **HOLE_CONFIRMED_NO_CHILD**
- children_found: 0
- incident: PRODUCTION_CONTINUITY_GAP — not a Mac catch-up miss; never invent 717

## D — Compression + fidelity

- packet vs UTF-8 L4: {'ref_bytes': 294, 'cand_bytes': 44, 'reduction_pct': 85.034}
- bundle vs UTF-8: {'ref_bytes': 294, 'cand_bytes': 2415, 'reduction_pct': -721.4286}
- fidelity beaucoup≠peu: **True**
- distinct fidelity bags: 4
- official_global_pct: None

Never invent block 717.

