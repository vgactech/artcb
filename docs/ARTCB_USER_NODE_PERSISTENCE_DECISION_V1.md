# R348b — Persistence decision + adversarial scope

**UTC:** 2026-09-14T17:55:00Z  
**CERTIFIED_100:** false · **UNIQUE_HUMAN:** false  
**R345:** untouched · **R347:** reference

## Formal persistence decision

| Mode | Meaning | Status |
|---|---|---|
| **LOCAL_NODE** (current) | `data/identity/user_node_associations.json` on one node; upsert rewrite | **IMPLEMENTED / LIVE probe PASS** |
| **REPLICATED_PROTOCOL** (target) | Verifiable association event replicated (PBFT/public ledger or signed gossip) | **DECIDED as next protocol work — NOT_IMPLEMENTED** |

### Decision (operator architecture)

For ARTCB multi-machine case (A owns several nodes; B associates without collapsing User/Wallet/Node/Device):

> **Target = REPLICATED_PROTOCOL association event.**  
> Current LOCAL_NODE scaffold is acceptable as **CODED + locally tested**, not as network certification.

Rationale: A↔B across nodes requires the same association evidence on N1…N4, not four divergent JSON files.

Local-only remains useful for lab / single-operator nodes, but must stay labeled `persistence=LOCAL_NODE`.

## Adversarial matrix

| Attack | Expected | Status |
|---|---|---|
| Replay challenge | reject | PASS unit + live |
| Expired challenge | reject | PASS unit |
| Sig for NODE-A used as NODE-B | reject | PASS unit |
| Role tamper after sign | reject | PASS unit |
| user_address tamper | reject | PASS unit |
| node_wallet tamper | reject | PASS unit |
| seed_hex in body | reject | FIXED raw-body scan (R348b) |
| Multi-node same association | equal state ×4 | **NOT_PROVEN** (needs REPLICATED_PROTOCOL) |
| Revocation / reassociation | policy | **NOT_PROVEN** |
| Compromised node / backup restore | policy | **NOT_PROVEN** |

## Live notes (this turn)

- Apex challenge/associate/status **HTTP 200** on `c5ea45b…`
- Replay → `challenge_unknown`
- n3/n4 challenge **200** (distinct `node_id` — local stores diverge by design today)
- Prior R348 prompt ingest **409 not_extending** remains honest gap for that ingest, not for the association API itself

## Non-claims

Association ≠ wallet ownership (R349) · ≠ UNIQUE_HUMAN · ≠ TPM · ≠ CERTIFIED_100
