# DV-05 — consensus Byzantine explicite (choix C)

Live engine: prepare/commit over HTTP between protocol-compatible peers
(`src/artcb/consensus/live_bft.py`). Bound: **N >= 3F+1**, **Q = 2F+1**.
Four live machines: **N=4, F=1, Q=3**.

Scope: **settlement WorkID uniqueness**, not PBFT for `append_block`
(public chain remains longest valid hash).

PASS only after live scenarios on the four VMs:

- honest propose
- double-proposal (same WorkID, different SettlementID) rejected
- one node offline, remaining Q still commits
- unroutable delay/timeout
- offline node recovers

`certified_distributed_mainnet` stays false until DV-01…DV-07 are all PASS
and economic V-01…V-07 are locked (D-043). See D-042 / D-043. DV-02 C
flood/chaos is still the remaining certification blocker.
