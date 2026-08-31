# DV-03 — compatibilité protocolaire (choix B)

Peers may differ in git SHA. They must match `network_id`, `protocol_version`, `genesis_hash`.
Missing fields (legacy OVH1) = not compatible. No silent match.

Expected live: OVH2 + AWS3 match `174-devnet-1`; OVH1 lacks fields → PARTIAL.
