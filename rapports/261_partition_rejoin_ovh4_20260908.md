# Rapport 261 — Partition réseau réelle + rejoin (OVH4 vivant)

**Date :** 2026-09-08T11:44Z → 11:47Z  
**Contact :** `official@artcb.space`  
**260 reste le PASS Byzantine input/rejection live.** On ne le rejoue pas.  
**Pas de wipe.** Pas de `systemctl stop`. GO-E produce **off**.  
**Pas PBFT. Pas producteur tué. Pas deux nœuds coupés.**

---

## 260 verrouillé (non rejoué)

> PASS — Byzantine rejection + evidence + live 4-node convergence + continued progress.  
> PAS ENCORE — PBFT / consensus Byzantine complet.

SHA de cette preuve 260 (chaque `/health`, pas seulement le SHA attendu) :  
**`6229a1c9f95baccefe617cf8bbe6327b13b78645` ×4**. Height alors **1079**, tip `bca7c61d…`.

---

## Ce que 261 démontre (complémentaire)

259 = **crash** (`systemctl stop`, `:8000` mort).  
261 = **partition** : le process OVH4 reste **UP**, `curl 127.0.0.1:8000/health` = healthy, l’opérateur joignait encore `:8000` depuis l’agent, mais les **3 IPv4 officielles** étaient DROP iptables `:8000,:8443` (commentaire `artcb261`).

```
OVH4 process UP
   │
   ├── agent → :8000 = 200   (pas un crash)
   └── OVH1/2/AWS3 → :8000 = unreachable / ConnectTimeout
```

Puis : les 3 continuent → mémo → replica 2+3 → restore iptables → catch-up OVH4.

---

## SHA mesuré à chaque phase (preuve rattachée à la version)

Chaque ligne = `GET :8000/health` **de ce nœud**, pas une copie du SHA attendu.

| Phase | OVH1 | OVH2 | AWS3 | OVH4 |
|---|---|---|---|---|
| Avant isolate | `6229a1c9f95baccefe617cf8bbe6327b13b78645` | idem | idem | idem |
| Pendant isolate | idem | idem | idem | idem + **process active**, livre **1079** |
| Après rejoin | idem | idem | idem | idem |

---

## 1. Avant (4 up)

Height **1079**, tip `bca7c61dfa0a72cbee0d7cb10787e89613acd3155d81f5cf68226ad7c32cf9ff`, `chain_valid=true`, liveness `reachable=4 partitioned=false`.  
OVH4 `wc -l` = **1079**, `artcb=active`, iptables `artcb261` = **0**.

---

## 2. Isolate

`scripts/artcb261_partition_ovh4.sh isolate` sur `ubuntu@91.134.45.8`.  
6 règles DROP (INPUT+OUTPUT × 3 peers, dports 8000,8443). Livre **non touché**.

| Vue | `agent :8000` | height | liveness |
|---|---|---|---|
| OVH1 / OVH2 / AWS3 | 200 | 1079 | `reachable=3` `partitioned=false` `q=3` (Q tient) |
| OVH4 | **200** (process up) | 1079 | `reachable=1` `partitioned=true` `below_quorum=true` |
| OVH4 localhost | healthy `6229a1c9…` | 1079 lignes | active |

Majorité : pas « partitioned » au sens du détecteur (`reachable < Q`).  
Isolé : oui. C’est le détecteur actuel, pas un mensonge.

---

## 3. Progression des 3 pendant la coupure

`POST /ai/memo` OVH1 HTTPS : HTTP **200**, dur **710 ms**.  
`block_index` **1079**, hash **`130882e0034f001abcca0e78b8cac4d0b6eb3c2835910d0ac013da348daac39f`**, graph `ai_memo_87ea9bd92041`.  
OVH1 height **1080**.

Replica localhost OVH1 :

| Pair | ok | avant → après | note |
|---|---|---|---|
| ovh-node-2 | true | **1079→1080** | same tip `130882e0…`, rtt **447.47 ms** |
| aws-node-3 | true | **1079→1080** | rtt **332.23 ms** |
| ovh-node-4 | **false** | — | `probe.error=ConnectTimeout` port 8000 |

OVH4 resté **1079** / tip `bca7c61d…` / `wc -l=1079` / **active**. Pas de wipe.

---

## 4. Restore + rejoin

`artcb261_partition_ovh4.sh restore` → **RULES=0**.  
Health agent OVH4 : healthy `6229a1c9…`.

Replica : OVH4 **1079→1080**, imported 1, rtt **386.86 ms**, même tip `130882e0…`. OVH2/AWS3 `nothing_to_send`.

---

## 5. Après (2026-09-08T11:46:56Z)

| Nœud | `/health` git_sha | height | last_hash | `wc -l` | liveness |
|---|---|---|---|---|---|
| ovh-node-1 | `6229a1c9f95baccefe617cf8bbe6327b13b78645` | **1080** | `130882e0034f001abcca0e78b8cac4d0b6eb3c2835910d0ac013da348daac39f` | **1080** | `reachable=4` |
| ovh-node-2 | `6229a1c9f95baccefe617cf8bbe6327b13b78645` | **1080** | même | **1080** | idem |
| aws-node-3 | `6229a1c9f95baccefe617cf8bbe6327b13b78645` | **1080** | même | **1080** | idem |
| ovh-node-4 | `6229a1c9f95baccefe617cf8bbe6327b13b78645` | **1080** | même | **1080** | idem |

`chain_valid=true`. iptables 261 = 0. OVH4 **active**.

---

## Verdict 261

| Propriété | Résultat |
|---|---|
| Process isolé toujours vivant | PASS live (agent `:8000` 200, localhost healthy) |
| Communication officielle coupée | PASS live (replica `ConnectTimeout`, pulses unreachable) |
| Les 3 continuent | PASS live (mémo 1080 + replica 2+3) |
| Livre isolé conservé | PASS observé (1079 lignes, pas de wipe) |
| Rejoin / catch-up | PASS live (1079→1080, même tip) |
| SHA ×4 enregistré | PASS (table ci-dessus) |
| PBFT / quorum de bloc | **NON** |
| Arrêt brutal du **créateur** (OVH1) | **NON** (volontairement OVH4) |
| Partition de 2 nœuds / fork distribué | **NON** |
| Evidence 260 persistante/répliquée/on-chain | **non audité ici** |

Vocabulaire : **PASS partition réseau 1 nœud + continuité 3/4 + rejoin catch-up**.  
Pas ~~PASS PBFT~~. Pas un second 259 (crash). Pas un second 260 (offres Byzantine).

Tests locaux : `tests/test_e2e261_partition_observe.py` — majorité 3/4 `partitioned=false` ; vue isolée 1/4 `partitioned=true`.

---

## Interdit (rappel)

Laisser les règles `artcb261` en place. Wipe. Relancer 260. Inventer un SHA. Stopper OVH1 « pour voir » sans rapport dédié. Afficher le token.
