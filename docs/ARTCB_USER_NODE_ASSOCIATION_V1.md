# R348 — USER ↔ NODE association API (spec + scaffold)

**UTC:** 2026-09-14T17:50:00Z  
**CERTIFIED_100:** false · **UNIQUE_HUMAN:** false  
**R345:** untouched (`CLIENT_DEVICE_BINDING_PASS`)

## Cross-audit (four surfaces)

| Surface | Path | Role in R348 |
|---|---|---|
| `/wallet/create` | `routes.py` | Still DEVICE_CLIENT bind only — **not** User↔Node |
| `HumanRegistry` | `economics/identity.py` | Still **not** required for association scaffold |
| `NodeIdentity` | `p2p/node_identity.py` | Supplies `node_id` + optional operator wallet |
| `device_wallet_limit` | `wallet_device_binding.py` | Remains client anti-abuse — **not** used here |

## API

### `GET /api/v1/identity/user-node/challenge`

Returns `{challenge, node_id, node_wallet_address, expires_in, protocol}`.

### `POST /api/v1/identity/user-node/associate`

Body (JSON):

```json
{
  "user_address": "artcb1…",
  "user_public_key_hex": "…",
  "challenge": "…",
  "signature_hex": "…",
  "role": "client"
}
```

Signed message (UTF-8):

```text
r348-user-node-association-v1|{challenge}|{node_id}|{node_wallet}|{user_address}|{role}
```

**Forbidden keys** (HTTP 400): `seed_hex`, `private_key`, `secret`, …

### `GET /api/v1/identity/user-node/status`

Lists local associations for this node (or filter `user_address=`).

## Explicit non-claims

- Association ≠ wallet ownership (R349)
- Association ≠ UNIQUE_HUMAN
- Association ≠ TPM/EK
- Does not change `/wallet/create` limits

## Code

- `src/artcb/identity/user_node_association.py`
- `src/api/user_node_routes.py`
