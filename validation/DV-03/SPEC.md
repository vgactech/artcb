# DV-03 — compatibilité protocolaire (choix B)

Peers may differ in git SHA. They must match `network_id`, `protocol_version`, `genesis_hash`.
Missing fields (legacy node) = not compatible. No silent match.

Historical D-040/D-041: four nodes advertised
`174-devnet-1` / `artcb-devnet-1` / `genesis-artcb-v2` → **PASS**.

D-043 live identity: `189-mainnet-1` / `artcb-mainnet-1` /
`genesis-artcb-mainnet-1`. Git SHA may differ; peers must still match
the three protocol fields. Not certified mainnet.
