# R327 — causal audit PBFT stall @1140 (R327_20260912T022024Z_a0e9f58e877e)

`commit_sha` = `a0e9f58e877ef286805ca8393eafe9b5695d95ff`

`CERTIFIED_100=false`

## Verdict

**Mac+n4 as cause of stall = NOT_ESTABLISHED.**

Established failure mode for public writes via artcb.me: `409 not_extending` (private suffix height vs public tip on primary).

Manual view-change works; public 1141 certified on n2/n3/n4; ovh1 cannot import while private tip diverges.

## Facts

- cert 1140 replicas: `['aws-node-3', 'ovh-node-1', 'ovh-node-2', 'ovh-node-4']` (Mac in cert: False)
- SSH journals: NOT_REACHABLE from this LAN

## Do not

- wipe OVH1
- invent 717
- remove Mac from membership without normative observer rule + evidence

