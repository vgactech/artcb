# Rapport 188 — BFT live 4 nœuds, pas de mainnet certifié

**Horodatage :** 2026-09-01T18:19:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)

## Demande

Lancer le mainnet immédiatement. Culture projet : ne pas inventer un PASS, ne pas renommer `174-devnet-1`, ne pas geler V-01…V-07 (D-026), ne pas fermer la fenêtre Ed25519 (D-032).

## Avant / après

| Surface | Avant | Après |
|---------|-------|-------|
| `src/artcb/consensus_spec.py` `LIVE_BFT_IMPLEMENTED` | `False` | `True` (prepare/commit live) |
| `/api/v1/consensus/*` | absent | status / prepare / commit / propose |
| Live 4 nœuds N/F/Q | non mesuré | **N=4 F=1 Q=3** |
| DV-05 | BLOCKED | **PASS** (e2e188 `20260901T181738Z`) |
| `certified_distributed_mainnet` | false | **false** (DV-01/02/06/07 + économie) |
| `network_id` | `artcb-devnet-1` | inchangé |

Bug vu en live : `/health` 500 (`from artcb.consensus_spec` hors PYTHONPATH nœud). Corrigé (import `src.artcb` + health ne doit plus 500).

## Scénarios e2e188 (mesurés)

- honest : `ok=true` prepared=4 Q=3
- double-proposal : `ok=false` `no_majority`
- OVH4 OFF : prepared=3 encore `ok=true`
- OVH4 recover : consensus/status 200
- delay 192.0.2.1 : timeout

## Ce qui n’est **pas** le mainnet

Les 8 blocs publics contiennent des sondes PRE-DV-04 / DV-04. Ce n’est pas une genèse mainnet. `append_block` n’est pas du PBFT. V-01…V-07 provisoires. DV-01 PENDING (TPM). DV-02/06/07 PARTIAL.

PR : https://github.com/vgactech/artcb/pull/44
