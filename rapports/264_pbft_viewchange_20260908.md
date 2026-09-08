# Rapport 264 — PBFT view-change live (VIEW-CHANGE Q=3 + NEW-VIEW)

**Date :** 2026-09-08T13:37Z → 13:40Z  
**Contact :** `official@artcb.space`  
**259–263 restent verrouillés.** On ne les rejoue pas.  
**Pas de wipe.** iptables `artcb264` **retirées**. **Aucun processus tué.**  
Ce n’est **pas** un 2f+1 sur `append_block`. `certified_distributed_mainnet` reste false (DV-02).

SHA code déployé pendant les mesures : **`202691252f73ae5c0f67e2ae360073ab4979f3ee`** ×4.

JSON brut : `logs/264_pbft_20260908T133746Z.json`.

---

## Protocole / autoprompt (réflexe)

Gravé **le jour même** dans :

- `.cursor/rules/artcb-live-node.mdc` — PBFT view-change se **code et se mesure** ; processus restent UP
- `AUTO_PROMPT_ARTCB` — entrée 2026-09-08T13:30Z + chiffres live
- `docs/PROTOCOL_SOURCE_OF_TRUTH.md` — rapport 264
- `LISTE_TESTS_ARTCB.md` — T-E52 `[x]`

Consigne répétée, maintenant dans le protocole : **inclure le PBFT** = VIEW-CHANGE Q=3 + NEW-VIEW mesurés dans le même tour. Interdit de clôturer par « non revendiqué ».

---

## Questions — résultats live

| Question | Résultat | Preuve mesurée |
|---|---|---|
| View-change PBFT implémenté ? | **OUI** | `src/artcb/consensus/pbft_view.py` + routes `/api/v1/consensus/pbft/*` |
| VIEW-CHANGE Q=3 signés ? | **OUI** | 3 messages `kind=view-change` HTTP 200 ; `vc_verified=[true,true,true]` ; replica_ids ovh-node-2, aws-node-3, ovh-node-4 |
| NEW-VIEW signé par le nouveau primary ? | **OUI** | HTTP 200, view **1**, primary **ovh-node-2** ; `new_view_verified=true` ; `vc_digest=45c456ba13f62678772f731936022f8a0495d8318f8c89f9ab1262a13327dc11` |
| Majority sur la nouvelle vue ? | **OUI** | ovh-node-2 / aws-node-3 / ovh-node-4 **view=1** pendant isolation |
| Prepare ancienne vue rejetée ? | **OUI** | work `artcb264-old-d3efee69` view=0 : **prepared=0** ; 409 `wrong_view` ×3 |
| 188 nouvelle vue Q=3 ? | **OUI** | work `artcb264-new-a6ed9b37` view=1 : **prepared=3 commits=3** (OVH2, AWS3, OVH4) |
| Primary isolé, processus UP ? | **OUI** | OVH1 `ARTCB=active` `/health` 200 pendant isolation ; view restée **0** ; BOOK **1086** ; RULES=6 `artcb264` |
| Restore + catch-up ? | **OUI** | restore `RULES=0` ; NEW-VIEW installé sur OVH1 → view **1** ; 4/4 view=1 primary=ovh-node-2 |
| 4 processus actifs, iptables 0 ? | **OUI** | `systemctl is-active artcb` = active ×4 ; R264=0 ×4 ; R261=0 ; R263=0 |
| Mémo on-chain + replica ? | **OUI** | index **1086** hash `1332be898f42cd91ccebb69eb8b38e909e79c0d087bec69348d931684bef6be8` ; replica OVH1 → **1087 ×4** même tip |

---

## 1. Déploiement

`git push origin HEAD:main` du feat(264) puis follow-main ×4. Keep-book : livres **1086** lignes au restart, pas de wipe, pas de genesis.

| Nœud | `/health` git_sha | `/etc/artcb/official_node` | artcb |
|---|---|---|---|
| ovh-node-1 | `202691252f73ae5c0f67e2ae360073ab4979f3ee` | ovh-node-1 | active |
| ovh-node-2 | idem | ovh-node-2 | active |
| aws-node-3 | idem | aws-node-3 | active |
| ovh-node-4 | idem | ovh-node-4 | active |

`GET /api/v1/consensus/pbft/view` avant : **view=0 primary=ovh-node-1** ×4, `replica_id` officiel ×4, `q=3`, `processes_stay_up=true`.

---

## 2. Isolation du primary (processus UP)

Primary de la vue 0 = **ovh-node-1**.  
`scripts/artcb264_partition_primary.sh isolate` vers 151.80.107.29, 51.44.222.232, 91.134.45.8 ports 8000,8443. Commentaire **artcb264**.

Pendant : `ARTCB=active`, `/health` HTTP 200 (l’agent n’est pas une IP officielle DROP), BOOK=1086, RULES=6.

---

## 3. VIEW-CHANGE + NEW-VIEW

Majorité (OVH2, AWS3, OVH4) :

- `POST /api/v1/consensus/pbft/view-change` `{view:1, reason:primary_unreachable}` → HTTP 200 ×3
- fan-in `/view-change/receive` → ok ×2 par nœud
- `POST /api/v1/consensus/pbft/new-view` sur **ovh-node-2** (primary de la vue 1) → NEW-VIEW signé
- install NEW-VIEW sur AWS3 et OVH4 → view=1

`GET /api/v1/consensus/pbft/view-changes?view=1` (OVH2) : `ok=true count=3 q=3` replica_ids `ovh-node-2, aws-node-3, ovh-node-4` digest `45c456ba13f62678772f731936022f8a0495d8318f8c89f9ab1262a13327dc11`.

Isolé OVH1 : toujours view=0.

---

## 4. 188 gated par la vue

| Phase | view | prepared | commits | détail |
|---|---|---|---|---|
| Ancienne vue (majorité) | 0 | **0** | 0 | 409 `wrong_view` ×3 |
| Nouvelle vue (majorité) | 1 | **3** | **3** | Q=3 formé |

Ce n’est **pas** un quorum sur `append_block`.

---

## 5. Restore, catch-up, mémo, replica

Restore iptables `artcb264` : RULES=0, artcb active, BOOK=1086 sur OVH1 au moment du restore.  
`POST /pbft/new-view` sur OVH1 → view=1.  
4/4 : view=1, primary=ovh-node-2.

Mémo public tags `264,pbft,view-change` session `264-pbft` :

- `block_index` **1086**
- `block_hash` **`1332be898f42cd91ccebb69eb8b38e909e79c0d087bec69348d931684bef6be8`**
- contenu : `view 0→1 primary ovh-node-1→ovh-node-2 vc=3 vc_digest=45c456ba… 188_old_prepared=0 188_new_ok=True processes_up=true`

`POST /p2p/replica/run` localhost OVH1 (python3 -c + stdin, pas un heredoc) : peers 2/3/4 `ok=true`.

Chaîne après replica :

| Nœud | height | last_hash | chain_valid | artcb | R264 |
|---|---|---|---|---|---|
| ovh-node-1 | **1087** | `1332be898f42cd91ccebb69eb8b38e909e79c0d087bec69348d931684bef6be8` | true | active | 0 |
| ovh-node-2 | **1087** | idem | true | active | 0 |
| aws-node-3 | **1087** | idem | true | active | 0 |
| ovh-node-4 | **1087** | idem | true | active | 0 |

---

## Matrice protocolaire

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| VIEW-CHANGE Q=3 + NEW-VIEW | consigne opérateur (pas D-0xx) | Castro-Liskov N=4 F=1 Q=3 | `src/artcb/consensus/pbft_view.py` | `tests/test_e2e264_pbft_viewchange.py` 16 passed avec 188/263 | SHA `2026912` ×4 view 0→1 |
| Processus restent UP | consigne opérateur | isolation iptables 261/264 | `scripts/artcb264_partition_primary.sh` | live `ARTCB=active` pendant DROP | RULES=6 puis 0 |
| Prepare ancienne vue | consigne opérateur | — | `LiveBftEngine.prepare_local(..., view=)` | unit `wrong_view` | prepared=0 |
| Pas append_block 2f+1 | D-032 / DV-05 scope | — | `not_block_append_bft=true` | — | livres append longest chain (mémo 1086) |

T-E52 `[x]`. Pas une D-0xx.
