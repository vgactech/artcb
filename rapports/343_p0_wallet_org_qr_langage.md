# R343 — P0 parallel: wallet 409 UX + ORG/KYB + QR pairing + langage battery

**UTC:** 2026-09-14T16:55:00Z  
**CERTIFIED_100:** false · **BETA:** true

## Accord opérateur

- ORG KYB = couche **distincte** de validation humaine
- `ORG_CREATED ≠ ORG_VALIDATED ≠ ORG_REWARD_ELIGIBLE`
- Pas d’auto-validation créateur ; UBO + conflit d’intérêts
- Documents privés + hash public
- Wallet « tous les noms existent » = **mauvais mapping 409** (device limit → message nom)
- QR téléphone = authenticator WebAuthn, pas simple caméra ; anti-rejeu
- Langage IA : fondation ≠ validé live ; bridges prog = chantier

## P0-1 Wallet — root cause + fix

| Avant | Après |
|---|---|
| Tout HTTP 409 → « nom existe déjà » | `device_wallet_limit` vs `wallet_name_exists` |
| Anti-fraude 1 wallet/appareil masqué | Message honnête + hint |

Tests: `tests/test_r343_wallet_create_errors.py` (PASS)

## P0-2 QR pairing — scaffold

`src/artcb/auth/qr_pairing.py` — session TTL≤120s, single-use, capability matrix  
E2E live téléphone : **NOT_PROVEN**

## P0-3 ORG/KYB — spec + model

`docs/ARTCB_ORG_KYB_V1.md` + `src/artcb/org/kyb.py`  
KYB complet live : **NOT_PROVEN**

## P1 Langage IA battery

`src/artcb/reasoning/langage_battery.py` — T1…T12 statuses  
Native A→B live : **NOT_PROVEN**

## Ouverts

#86 ACL · #77 N04/C04 · Anti-Sybil≥50 · QR E2E · KYB validators · bridges Python/TS · CERTIFIED_100
