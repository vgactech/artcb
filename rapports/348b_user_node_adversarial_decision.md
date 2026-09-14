# R348b — adversarial + persistence decision

**UTC:** 2026-09-14T17:55:00Z  
**CERTIFIED_100:** false · **UNIQUE_HUMAN:** false

## Accord audit

R348 = évolution cohérente, **pas** certification réseau.  
Store = **LOCAL_NODE** (upsert JSON), pas append-only blockchain.

## Décision formelle

**Cible = REPLICATED_PROTOCOL** (événement d’association vérifiable/répliqué).  
**Actuel = LOCAL_NODE** (scaffold live OK pour challenge/associate/replay).

## Livré R348b

- Tests adversariaux (replay, expiry, node/role/address/wallet tamper)
- Scan raw body → refuse `seed_hex` (Pydantic ne peut plus l’ignorer)
- Label `persistence=LOCAL_NODE` dans les réponses
- Doc décision `docs/ARTCB_USER_NODE_PERSISTENCE_DECISION_V1.md`

## Live (apex `c5ea45b`)

challenge/associate/status 200 · replay 400 · n3/n4 challenge 200 (stores locaux distincts)
