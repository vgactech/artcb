# Rapport 263 — Complétude A→Z live (188, attest, 2 byz, 2 producteurs, partition 2)

**Date :** 2026-09-08T13:00Z → 13:20Z  
**Contact :** `official@artcb.space`  
**259–262 restent verrouillés.** On ne les rejoue pas.  
**Pas de wipe.** iptables `artcb261`/`artcb263` **retirées**. Clé temporaire OVH2 **effacée**.  
**Pas un view-change PBFT.** `certified_distributed_mainnet` reste false.

SHA code déployé pendant les mesures : **`856c0ee96423d948c150ac1375d3f855dfde1a25`** ×4.

---

## Protocole / autoprompt (réflexe)

Gravé **le jour même** dans :

- `.cursor/rules/artcb-live-node.mdc` — section **Complétude A→Z**
- `AUTO_PROMPT_ARTCB` — entrée 2026-09-08
- `docs/PROTOCOL_SOURCE_OF_TRUTH.md`

Consigne répétée, maintenant dans le protocole : **ne jamais terminer un tour** par « NON démontré / il reste » sans exécuter la boucle live suivante **dans le même tour**. Encoder ici toute nouvelle répétition opérateur sans qu’on le redemande. Partition 2 nœuds autorisée **seulement** si restore. Pas de PASS PBFT inventé.

---

## Questions — résultats live (aucun « reste à »)

| Question | Résultat | Preuve mesurée |
|---|---|---|
| Evidence persistente ? | **OUI** | JSONL `data/consensus/byzantine_evidence.jsonl` |
| Evidence authentifiée ? | **OUI** | sidecar signé chaîne ; `GET` `authenticated=true` ×4 après `POST /evidence/sign` |
| Evidence répliquée ? | **OUI** | merge append-only ; counts live **36 / 36 / 52 / 52** |
| Evidence falsifiable sur disque ? | **OUI** | tamper OVH4 → `tampered=true` `authenticated=false` ; restore → `authenticated=true` |
| Evidence supprimable puis récupérable ? | **OUI** | delete OVH4 count=0 ; replica → count **32** |
| Evidence on-chain ? | **OUI (digest ancré)** | mémo public index **1085** hash `a61c5c40684eb74c62fc01754eedb99e65c161b6260d65dc0b6949fbc3151508` — le JSONL n’est pas un bloc ; `signed_on_chain` du store reste false |
| 188 Q=3 settlement ? | **OUI mesuré** | agent `:8000` ×4 : **prepared=4 commits=4** avant et après partition |
| 188 mesh depuis OVH1 ? | **OUI mesuré** | avant/après : prepared=4 commits=4 ; **pendant partition 2 : prepared=2** (AWS3+OVH4 `URLError`) &lt; Q=3 |
| Tip-attest Q=3 ? | **OUI** | 4 signatures valides, même `(height, hash)` ; **pas PBFT** |
| 2 senders Byzantine ? | **OUI reject-only** | `from_node_id` ovh-node-4 + aws-node-3 ; `hash_mismatch` ; **0 append** |
| 2 producteurs concurrents ? | **OUI mesuré** | OVH1+OVH2 index **1084** hashes **différents** (fork réel) puis convergence |
| Partition 2 nœuds + restore ? | **OUI** | AWS3+OVH4 isolés ; liveness majority `reachable=2 partitioned=true q=3` ; RULES=0 ; artcb active ×4 |
| View-change PBFT ? | **NON** (honnête) | non implémenté ; non revendiqué |

---

## 1. Tip-attest Q=3

`GET /api/v1/consensus/tip-attest` sur `:8000` ×4.

Après close-out (hauteur finale) :

| | |
|---|---|
| `valid_signatures` | **4** |
| `quorum_count` | **4** (≥ Q=3) |
| height | **1086** |
| last_hash | `a61c5c40684eb74c62fc01754eedb99e65c161b6260d65dc0b6949fbc3151508` |
| `not_pbft_view_change` | true |

Vérification agent : jambe Ed25519 de l’enveloppe hybride (liboqs absent sur l’agent ; D-032 B encore ouverte). Les nœuds signent **hybrid** ML-DSA-65+Ed25519.

---

## 2. 188 prepare/commit

Agent coordinateur (atteint les 4 processus même si le mesh officiel est coupé) :

| Phase | prepared | commits | ok |
|---|---|---|---|
| Avant partition | 4 | 4 | **true** |
| Pendant partition 2 | 4 | 4 | true (l’agent n’est pas une IP officielle DROP) |
| Après restore | 4 | 4 | **true** |

Mesh coordinateur **OVH1 → :8000 ×4** (DROP iptables visible) :

| Phase | prepared | rejected | ok |
|---|---|---|---|
| Avant | 4 | [] | **true** |
| Pendant | **2** (OVH1, OVH2) | AWS3+OVH4 `URLError` | **false** — Q=3 non formé |
| Après | 4 | [] | **true** |

Scope : **settlement** uniqueness. Append de bloc = plus longue chaîne valide. **Pas un view-change PBFT.**

---

## 3. Deux senders Byzantine

`POST /p2p/blocks/offer` OVH1, `from_node_id` `ovh-node-4` puis `aws-node-3`, payloads `ff…` / `ee…`.

Décisions : `reject` / `hash_mismatch` ×2. `imported=0`. Tip inchangé au moment du probe (`31bb77a1…` height 1081). **0 append.**

---

## 4. Evidence

Tamper live OVH4 : `tampered=true`, `authenticated=false`. Restore fichier : `authenticated=true`. Delete : count=0. Replica : count=32.

Close-out `POST /evidence/sign` ×4 : `authenticated=true` `tampered=false`. Counts **36 / 36 / 52 / 52** (merge, pas d’écrasement).

Ancre mémo : index **1085**, hash `a61c5c40…`, graph `ai_memo_…` (runner 13:13Z).

---

## 5. Partition 2 nœuds (AWS3 + OVH4)

Script `scripts/artcb263_partition_node.sh` comment `artcb263`. Processus **UP**. Livre non touché.

Pendant :

- Liveness OVH1 et OVH2 : `n=4 q=3 reachable=2 below_quorum=true partitioned=true`
- Mémo OVH1 (majority write) HTTP 200
- Mesh 188 prepared=2

Restore : `RULES=0` ×2, `ARTCB=active`, artcb261=0.

---

## 6. Deux producteurs concurrents

OVH1 Bearer opérateur ∥ OVH2 clé temporaire `api_keys.json` (hash only, `/tmp/artcb263.key` 0600, **supprimée**).

| Writer | index | hash |
|---|---|---|
| ovh-node-1 | **1084** | `0290cf4f696026d87e4872fe14c5b2a915621adb29de6c39017146a505f1192a` |
| ovh-node-2 | **1084** | `b7b8b5239d3afe147672732b2bacb29537eecb495c208455992e5961a0e1871b` |

Fork réel au même index. Replica depuis OVH1 : AWS3+OVH4 prennent le tip OVH1. OVH2 refuse l’équivoque → rewind **une** dernière ligne (pas un wipe) puis replica. Close-out : **1086 ×4** même hash `a61c5c40…` `chain_valid=true`.

---

## 7. État final mesuré (close-out)

| Nœud | `/health` git_sha | height | last_hash | chain_valid | artcb | iptables 261/263 |
|---|---|---|---|---|---|---|
| ovh-node-1 | `856c0ee96423d948c150ac1375d3f855dfde1a25` | **1086** | `a61c5c40684eb74c62fc01754eedb99e65c161b6260d65dc0b6949fbc3151508` | true | active | — |
| ovh-node-2 | `856c0ee96423d948c150ac1375d3f855dfde1a25` | **1086** | `a61c5c40684eb74c62fc01754eedb99e65c161b6260d65dc0b6949fbc3151508` | true | active | — |
| aws-node-3 | `856c0ee96423d948c150ac1375d3f855dfde1a25` | **1086** | `a61c5c40684eb74c62fc01754eedb99e65c161b6260d65dc0b6949fbc3151508` | true | active | 0 / 0 |
| ovh-node-4 | `856c0ee96423d948c150ac1375d3f855dfde1a25` | **1086** | `a61c5c40684eb74c62fc01754eedb99e65c161b6260d65dc0b6949fbc3151508` | true | active | 0 / 0 |

Livres disque OVH1/OVH2 : **1086** lignes. Pas de wipe.

Tests locaux : `pytest tests/test_e2e263_close.py` — 8 passed. T-E51.

---

## Matrice protocole

| Règle | Décidée | Simulée | Codée | Testée | Live (SHA) |
|---|---|---|---|---|---|
| Complétude A→Z / ne pas clôturer incomplet | opérateur 2026-09-08 | — | `artcb-live-node.mdc`, `AUTO_PROMPT_ARTCB` | T-E51 | `856c0ee` ×4 |
| Tip-attest Q=3 | — | — | `tip_attest.py` `GET /tip-attest` | T-E51 | 4 sigs, height 1086 |
| Evidence signée + tamper | — | — | sidecar + `/evidence/sign` | T-E51 | authenticated ×4 |
| 188 Q=3 mesuré | D-042 / 188 | sim 188 | `live_bft.py` | T-E51 | prepared 4 ; mesh pendant partition prepared 2 |
| 2 byzantine senders | — | — | `/p2p/blocks/offer` | T-E51 | 0 append |
| 2 producteurs + fork recovery | — | — | replica + rewind 1 ligne | live | 1084 fork → 1086 ×4 |
| Partition 2 + restore | opérateur 263 | — | `artcb263_partition_node.sh` | live | RULES=0 |
| PBFT view-change | — | — | **non** | — | **non revendiqué** |

---

## Interdit

Inventer un PASS PBFT / view-change. Laisser iptables en place. Wipe `blocks.jsonl`. Afficher le token. Copier la clé nœud 1 dans Doppler 2/3/4. Clôturer sur une liste « NON démontré ».
