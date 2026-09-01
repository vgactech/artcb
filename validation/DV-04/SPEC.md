# DV-04 — replication d'état (choix C)

PASS only when **four protocol-compatible live machines** show the same
`last_hash` / `public_state_digest` after a controlled public transaction,
then after one node restart.

Current inventory (2026-09-01, D-040 + D-041):

| Node | Protocol | Counts for DV-04 C |
|------|----------|--------------------|
| OVH1 `152.228.144.34` | `174-devnet-1` (D-040 code, D-041 book) | yes |
| OVH2 `151.80.107.29` | `174-devnet-1` | yes |
| AWS3 `51.44.222.232` | `174-devnet-1` | yes |
| OVH4 `91.134.45.8` | `174-devnet-1` | yes |

Homogeneous set = 4 protocol-compatible nodes. OVH1 orphan genesis
`8d542e49` (2026-08-29) was **not merged**; the existing public book
genesis `cc61f710` was adopted (D-041). Wallets / `chain.key` kept.

PRE-DV-04 (3-node public tip) does not unlock DV-04 C by itself.
`certified_distributed_mainnet` stays false even if DV-04 PASS.
DV-05 stays BLOCKED until a live BFT engine exists.
