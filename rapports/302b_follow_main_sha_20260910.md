# 302b — follow-main ×4 après `07ed590`

**2026-09-10T11:36:00Z.** `CERTIFIED_100=false`. Jamais wipe. `blocks.jsonl` **1133** lignes ×4. `install.sh` / genesis / rescue **non** exécutés.

## Git

- `origin/main` poussé : `07ed59000139e81c7cffcd4d2fb810927c05f1b2` (`fix(302): keep live N from PBFT membership, not n_f_q(4)`).

## follow-main SSH (rc=0 ×4)

| Nœud | before | after HEAD | restart | BOOK |
|------|--------|------------|---------|------|
| ovh-node-1 | `e58dc28…` | `07ed590…` | yes | 1133 |
| ovh-node-2 | `07ed590…` | `07ed590…` | no (sha unchanged) | 1133 |
| aws-node-3 | `bc0a9b9…` | `07ed590…` | yes | 1133 |
| ovh-node-4 | `e58dc28…` | `07ed590…` | yes | 1133 |

Health immédiat post-restart : URLError (processus en cours de relance). Retry : **HTTP 200** `git_sha=07ed590…` sur OVH1, OVH2, AWS3, OVH4 et Mac `:8001`.

Log : `logs/302_follow_main_20260910T113537Z.json`.

Mac replica PBFT live (P2P/quorum) : **toujours NON PROUVÉ.** Health 200 + SHA égal ≠ certificat N=5.
