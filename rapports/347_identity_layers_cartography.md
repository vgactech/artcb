# R347 — Cartographie User ↔ Wallet ↔ Device ↔ Node

**UTC:** 2026-09-14T17:45:00Z  
**Accord audit opérateur :** Node ≠ User ; ne pas uploader clé privée ; R345 = CLIENT_DEVICE_BINDING_PASS seulement.

## Verdict

| Claim | État |
|---|---|
| Cartographie code | **DONE** (`docs/ARTCB_IDENTITY_LAYERS_V1.md`, `src/artcb/identity/layers.py`) |
| Invariants I1–I8 | **CODED + tested** |
| User↔Node signature association | **NOT_IMPLEMENTED** |
| HumanRegistry ↔ `/wallet/create` | **NOT_WIRED** |
| UNIQUE_HUMAN | **false** |
| CERTIFIED_100 | **false** |

## Finding principal

`HumanRegistry` / `DeviceRegistry` / `WalletIdRegistry` existent déjà dans `economics/identity.py` (mining/economics) mais **ne gouvernent pas** `POST /wallet/create`.  
La création wallet live est limitée par **DEVICE_CLIENT** (R345), pas par USER.

`/setup/init-node` crée le **wallet opérateur du nœud** — distinct conceptuellement des wallets clients, mais historiquement confondu via DEVICE_HOST (corrigé R345 pour le limiteur global).

## Prochaine implémentation (ordre)

1. API association User↔Node (challenge + signature, jamais privkey)  
2. Lier wallets à Human/User explicitement  
3. Garder `device_wallet_limit` comme anti-abus client  
4. UNIQUE_HUMAN / TPM / R344 réplication — chantiers séparés

Artefact machine : `logs/R347/identity_map.json`
