# ARTCB Identity Layers V1 (R347) — cartography + invariants

**UTC:** 2026-09-14T17:45:00Z  
**CERTIFIED_100:** false · **UNIQUE_HUMAN:** false  
**R345 label:** `CLIENT_DEVICE_BINDING_PASS` only

## Why this doc exists

`device_wallet_limit` must never mean:

> “server X already has wallet A ⇒ user B cannot create an account on artcb.me”

That conflates **Node / host** with **User**.

## Layers (never collapse)

| Layer | Meaning | Code today | Wired to `/wallet/create`? |
|---|---|---|---|
| **USER / HUMAN** | Economic subject | `HumanRegistry` (`economics/identity.py`) | **NO** |
| **WALLET** | Keypair + address | `WalletManager` | YES (creates) |
| **NODE** | P2P/operator id | `NodeIdentity` + `/setup/init-node` | Creates **operator** wallet only |
| **DEVICE_HOST** | Server machine | `DeviceIdentityStore` | **NO** after R345 (barred as global limiter) |
| **DEVICE_CLIENT** | Browser context | `UA\|X-ARTCB-Device-Id` + bindings | YES (R345 limit) |
| **AUTHENTICATOR** | WebAuthn / face | `webauthn_routes` | Creates wallet; **≠ UNIQUE_HUMAN** |

## Relations today (measured in code)

```text
NODE ──1──► operator WALLET     (init-node, .node_config)
DEVICE_CLIENT ──≤1──► WALLET    (wallet_device_bindings.json)  [anti-abuse]
AUTHENTICATOR ──► WALLET name   (credential store)
USER_HUMAN ──✘──► WALLET        (NOT WIRED at create)
USER_HUMAN ──✘──► NODE          (NO signature association API)
DEVICE_HOST ──► NODE process    (same AppState)
```

## Target relations (not yet implemented)

```text
USER signs challenge locally
        │
        ▼
UserPublicKey + NodePublicKey + signature + ts
        │
        ▼
Node verifies  →  User ↔ Node association
        │
        ▼
Wallets remain owned by USER (not by NODE)
```

**Never upload UserPrivateKey to the node.**

## Invariants (I1–I8)

See `src/artcb/identity/layers.py::INVARIANTS`.

Critical operational rule:

> Shared public node (artcb.me) may serve many users.  
> Node operator wallet ≠ every client wallet.  
> Client device binding ≠ HumanIdentity.

## What R345 fixed / did not fix

| Fixed | Not fixed |
|---|---|
| Host FP no longer blocks all users | HumanIdentity global uniqueness |
| Client A vs B can each create | TPM/EK attestation as economic root |
| Same client 2nd wallet → 409 | localStorage spoof / multi-browser Sybil |

## Next implementation order (do not skip cartography)

1. Keep this map authoritative  
2. Add `User↔Node` association API (challenge+signature)  
3. Bind wallets to `UserIdentity` / `HumanRegistry` explicitly  
4. Keep `device_wallet_limit` as **client anti-abuse** only  
5. Separately: UNIQUE_HUMAN / TPM / R344 replication
