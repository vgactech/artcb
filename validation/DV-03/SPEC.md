# DV-03 — compatibilité protocolaire (choix B)

Peers may differ in git SHA. They must match `network_id`, `protocol_version`, `genesis_hash`.
Missing fields (legacy node) = not compatible. No silent match.

Expected live after D-040: OVH1 + OVH2 + AWS3 + OVH4 all advertise
`174-devnet-1` / `artcb-devnet-1` / `genesis-artcb-v2` → **PASS**.
Git SHA may differ; currently they share the same tip.
