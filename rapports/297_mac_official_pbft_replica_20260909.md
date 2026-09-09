# 297 — Mac = nœud ARTCB officiel (même classe qu’OVH/AWS)

**Branche :** `cursor/pbft-r297-mac-replica-568e` depuis `origin/main` `05d703022a949a61849516e1c8ed20a4e715d9a7`  
**PR cible :** dédiée « MAC official PBFT replica » — **indépendante de PR #84**.  
**CERTIFIED_100=false.** N04 50 % FAIL **inchangé**.

## Correction opérateur (2026-09-09T21:55Z)

~~Le Mac attend `live_enrolled=False` / `ARTCB_MAC_PBFT_ENROLLED`.~~ **Refusé.**  
Ce n’est **pas** un observateur isolé. C’est un nœud comme OVH/AWS, via le chemin **clone GitHub + process node**.

Process local mesuré : `http://127.0.0.1:8001/health` **healthy**, `git_sha=05d703022a949a61849516e1c8ed20a4e715d9a7` = `origin/main`, branche process `cursor/pbft-r297-mac-replica-568e`. TPM absent (non bloquant).

## Membership adaptatif

`official_pbft_replica_ids()` = tous les `NodeSpec.pbft_replica=True` (ordre du registre).

Aujourd’hui : `ovh-node-1`, `ovh-node-2`, `aws-node-3`, `ovh-node-4`, `mac-node-local` → **N=5, f=1, Q=3**.

Un nouveau nœud (clone, VM, bare-metal, n’importe où) : `pbft_replica=True` → N grandit, `n_f_q(N)` recalcule f et Q.

Les 4 IPv4 publiques restent les **seeds** SSH / `:8000`. Ce n’est pas une exclusion du Mac. L’IP LAN n’est pas l’identité.

| Ensemble | Contenu |
|---|---|
| Seeds IPv4 / SSH remote follow-main | 4 VMs |
| `official_pbft_replica_ids()` | 5 (Mac inclus) |
| Mac `follow_main` | **true** (pull local, chemin clone) |
| `tunnel_required` | transport RFC1918, pas le rôle |

## Encore NOT_PROVEN (preuves live, pas le rôle)

- Clé publique Mac **écrite localement** dans `official_replica_keys.json` (n=5, prefix `ZAhGhokfvF/Y`, private non imprimée) — les 4 VMs n’ont pas encore ce SHA
- PREPARE / COMMIT / certificat avec `mac-node-local` dans `replica_ids`
- P2P bidirectionnel Mac ↔ 4 seeds (`:8000` R294 timeout)
- Même SHA **déployé** sur les 4 VMs (elles tournent encore le membership N=4 de `main`)
- Wallet possession, TPM (N/A)
- Thinking → ARTCB : **non**

`includes_thinking=false`. PR #84 hors sujet.
