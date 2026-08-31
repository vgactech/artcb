# DV-04 — replication d'état (choix C)

PASS only when **four protocol-compatible live machines** show the same
`last_hash` / `public_state_digest` after a controlled public transaction,
then after one node restart.

Current inventory (2026-08-31):

| Node | Protocol | Counts for DV-04 C |
|------|----------|--------------------|
| OVH1 `152.228.144.34` | legacy (no protocol_version) | **no** (D-036) |
| OVH2 `151.80.107.29` | `174-devnet-1` | yes |
| AWS3 `51.44.222.232` | `174-devnet-1` | yes |
| OVH4 `91.134.45.8` | `174-devnet-1` (after deploy) | yes |

Homogeneous set = 3. **DV-04 FINAL stays BLOCKED** until a fourth
protocol-compatible node exists (redeploy OVH1 only on explicit order).

PRE-DV-04 on the homogeneous triple is allowed and does not unlock DV-04 C.
