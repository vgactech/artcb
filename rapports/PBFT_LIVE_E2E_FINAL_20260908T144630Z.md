# Rapport PBFT_LIVE_E2E_FINAL_20260908T144630Z

**Date :** 2026-09-08T14:46Z → 14:53Z  
**Contact :** `official@artcb.space`  
**R264 = BASELINE**, pas cette certification.  
**Pas de wipe.** iptables `artcb265` **retirées**. Processus UP sauf TEST I (restart puis actif).  
**Traces nanoseconde** : `data/trace/ns.jsonl`, `unit=nanosecond`, `ts_ns` ≥ 10¹⁵.

Preuve brute : `logs/265_pbft_e2e_20260908T144630Z.json`

---

## A. Git SHA exact

| | SHA |
|---|---|
| `origin/main` / agent / 4 nœuds | **`f470d7b69104d54af4a1cbd9bbc9af06e0322b60`** |
| R264 mesuré | `202691252f73ae5c0f67e2ae360073ab4979f3ee` |
| Diff R264 → 3129ebe | **aucun fichier `src/`** (docs + runner replica seulement) |
| Diff 3129ebe → f470d7b | moteur 265 `pbft_finality.py` + routes + traces ns |

---

## B. Nœuds utilisés (interrogés indépendamment)

| Nœud | IPv4 `:8000` | SHA | artcb | BOOK |
|---|---|---|---|---|
| ovh-node-1 | 152.228.144.34 | `f470d7b6…` | active | 1091 |
| ovh-node-2 | 151.80.107.29 | idem | active | 1091 |
| aws-node-3 | 51.44.222.232 | idem | active | 1091 |
| ovh-node-4 | 91.134.45.8 | idem | active | 1091 |

Aucun mock. Chaque nœud a répondu son propre `/health`, `/chain/status`, `/pbft/view`, `/pbft/finality`, `/pbft/certificate?seq=1087`, `/trace`.

---

## C. Configuration

`N=4 F=1 Q=3`  
Primary = `OFFICIAL_COMPUTE_NODE_IDS[view % 4]`  
Avant : view **1** primary ovh-node-2. Après : view **2** primary aws-node-3.

---

## D. Architecture réellement testée

### Chemin exercé (live)

`POST /api/v1/consensus/pbft/propose` (primary, `append_block(dry_run=True)`)  
→ PRE-PREPARE signé + fan-out `/pre-prepare`  
→ `/prepare` Q=3  
→ `/commit` Q=3  
→ certificat  
→ `/certificate` + `write_certified_block` / `import_extending_block`  
→ même `hash` ×4

### View-change

Isolation iptables `artcb265` (processus UP)  
→ VIEW-CHANGE 264 Q=3 + VIEW-CHANGE 265 P-set  
→ NEW-VIEW  
→ restore  
→ catch-up ancien primary  
→ nouvelle proposition finalisée

### Ce qui n’est **pas** encore le chemin unique des mémos

`append_block` public (ex. `/ai/memo`) **écrit toujours localement** sans attendre le certificat. Seul `/pbft/propose` est le chemin PBFT. Un index **déjà certifié** ne peut plus être reorg (`pbft_finalized_conflict`).

---

## E. Résultats

| Test | Script | Preuve indépendante |
|---|---|---|
| A normal PRE-PREPARE→COMMIT | PASS | seq **1087** digest `e2055059bfcc259dff4b26fbd1ad87a7c48d5cba0ffd6d1524bf7e5d565429f7` cert Q=3 replica_ids 4/4 ; height **1088** ×4 ; `dur_ns=28034027022` ; traces `pbft_*` ×4 nœuds `ns_bad=0` |
| B primary isolé UP | PASS | ovh-node-2 isolé `/health` 200 ; VC264=3 ; view **1→2** primary aws-node-3 ; round seq **1088** hash `97ad7596f522a369e294e5b9ec0b37cfb5020d043054a68db56734b3ac4662c1` ×4 |
| C primary byzantin **signé** double proposition | PASS script (409 sur PP unsigned) | **Limite :** ce n’est pas deux PRE-PREPARE valides contradictoires signés par la clé du primary live. Le pytest local `test_c_equivocation_rejected` couvre l’émission primary. Live = rejet message invalide. |
| D view-change avec P-set | PASS script (VC265×3) | P-set = seq **1087** déjà **committé** en A. Pas une opération seulement préparée. |
| E NEW-VIEW Q&lt;3 / vide | PASS | HTTP 409/422 |
| F fausse signature | PASS | prepare `ok=false` / invalid |
| G Q impossible (2 nœuds) | PASS | round_ok **false** |
| H partition 2 + restore | PASS | 4/4 même tip après restore ; R265=0 |
| I restart replica | PASS | ovh-node-4 restart ; view **2→2** height **1089→1089** ; active |
| J double finalité / cert bidon | PASS script (cert vide 409) | Reorg d’un index certifié : pytest `test_j_finalized_index_cannot_be_replaced`. Live : 4 nœuds servent le **même** cert 1087. |
| K multi-view | PASS 1→2 | Pas 0→1→2→3 dans ce run (0→1 = R264). |
| L long run | PASS | 2 cycles `ok=true` `dur_ns≈28.2s` chacun ; height finale **1091** tip `42510680b64efd88f5b2802ef0363ff791ac720ad5b607b48063113be2b58f6b` ×4 `chain_valid=true` |

---

## F. Preuves brutes

- `logs/265_pbft_e2e_20260908T144630Z.json`
- `logs/265_pbft_e2e_latest.json`
- Sur chaque nœud : `data/trace/ns.jsonl` (`GET /api/v1/trace?limit=2000`)
- `data/consensus/pbft_finality.json` (4 certificats / nœud)
- `GET /api/v1/consensus/pbft/certificate?seq=1087` ×4 : digest `e2055059…` q=3

---

## G. Hashes critiques

| seq | digest / last_hash |
|---|---|
| 1086 (pré-265, mémo 264) | `1332be898f42cd91ccebb69eb8b38e909e79c0d087bec69348d931684bef6be8` |
| 1087 (A, certifié) | `e2055059bfcc259dff4b26fbd1ad87a7c48d5cba0ffd6d1524bf7e5d565429f7` |
| 1088 (B) | `97ad7596f522a369e294e5b9ec0b37cfb5020d043054a68db56734b3ac4662c1` |
| 1091 (après L) | `42510680b64efd88f5b2802ef0363ff791ac720ad5b607b48063113be2b58f6b` |

---

## H. Bugs rencontrés

1. `int(seq or -1)` cassait seq=0 (pytest empty chain). Corrigé `_iint` avant le live. Non-régression : `tests/test_e2e_pbft_finality.py`.
2. `GET /pbft/finality` omis après ajout de `/prepared`. Restauré. Test HTTP `test_http_propose_preprepare_on_primary`.

---

## I. Limites restantes (rien de caché)

1. **`append_block` des mémos n’est pas exclusif-PBFT.** Le chemin certifié live est `/pbft/propose`. Les blocs historiques &lt; 1087 n’ont pas de certificat.
2. TEST D n’a pas isolé une valeur **seulement préparée**.
3. TEST C live n’a pas fait signer deux digests par le primary réel.
4. TEST K : un seul saut de vue dans ce run.
5. `certified_distributed_mainnet` **reste false** (DV-02 flood/chaos). Ce rapport ne le lève pas.
6. Coordinateur agent pour le fan-out HTTP (comme 188). Les 4 processus signent réellement ; ce n’est pas un quorum calculé hors réseau.

---

## J. Verdict final

**`PBFT_LIVE_E2E_NOT_VALIDATED`**

au sens de la barre absolue du mandat (chemin unique d’append + double proposition primary live signée + P-set d’une valeur non encore commitée + 3 hops de vue dans le même run).

Ce qui **est** mesuré sur 4 machines réelles, SHA identique, traces ns, certificats Q=3, view-change avec processus UP, restart, partition 2 restorée, 4 certificats, tip unique 1091 : suite A/B/E/F/G/H/I/L **exécutée et recoupée nœud par nœud**. R264 n’est pas cette preuve. On ne déclare pas le mainnet BFT certifié.
