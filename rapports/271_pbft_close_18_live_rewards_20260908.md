# 271 — 18 preuves live + récompense réelle depuis le genesis

Date live : **2026-09-08**. Test mainnet (accès interne seulement). Pas de wipe. Pas de HPC. AWS **t3.small** `i-085b74abd1aaf04ee`.

SHA déployé pendant la campagne = `origin/main` du gel docs R270 :

**`4fb2b1bb567f29628bdd7b2427d6815f00097792`** ×4

Moteur PBFT inchangé : **`f59dd88dfacde1a898fd59b01040a02a59f7e3b2`**.

JSON brut : `logs/271_close_20260908T201920Z.json`  
Récompenses jsonl : `logs/271_rewards_live.json`  
Restore post-campagne : `logs/271_post_restore.json`

```text
CERTIFIED_100              = false
global_verdict             = NOT_CERTIFIED
PASS / FAIL / NOT_PROVEN   = 34 / 9 / 0   (43/43 exécutées)
BFT_SETTLEMENT 188         = PASS (cette campagne)
BFT_BLOCK_CONSENSUS        = PARTIAL
PRODUCTION_READY           = false
```

Les 25 PASS R270 sont **recopiés** (preuve SHA `8050981`, pas rejoués). Les 18 manquants ont été **exécutés** sur le WAN avec paquets réels. **Aucun FAIL n’a été transformé en PASS.**

---

## 1. Récompense de bloc depuis le premier bloc (mesure live, pas un slogan)

Formule **codée et branchée** (`emission.issued_reward_satoshi` → `ChainManager._calculate_block_reward`) :

\[
R(H)=50\left(\frac{\max(H,H_{REF})}{H_{REF}}\right)^{-\alpha}
\quad
H_{REF}=10^6
\quad
\alpha=\ln 50/\ln 64
\]

\[
R_{\text{bloc}}=\min\left(R(H)\times\frac{\Delta t_{\text{médian}}}{600},\; 21\,000\,000-S_{\text{émis}}\right)
\]

- `H_adult` live bootstrap = **0** → clamp à \(H_{REF}\) → **R(H) = 50 ARTCB**.
- `block_index` **ne réduit pas** R. Halving 210 000 **retiré** du chemin live.
- \(\Delta t_{\text{médian}}\) = médiane des intervalles **≥ 1 s** parmi les ~12 derniers timestamps (`_last_observed_interval_seconds`). Un burst sub-seconde est ignoré (plancher de mesure 1 s → \(50\times 1/600 = 0{,}08333333\) ARTCB = 8 333 333 sat).
- Un trou de plusieurs jours **n’émet pas** \(50 \times \Delta t_{\text{mur}}/600\). La médiane récente borne le scale.
- **Un seul budget** par bloc : `settle_block(block_reward, …)` découpe HBP / PoL / provider / worker. On n’additionne pas 50+10+20 comme création nouvelle.

Mesure jsonl OVH1 après restore (hauteur **1109**, 1109 lignes, indices 0…1108) :

| Grandeur | Valeur mesurée |
|---|---|
| Somme émise | **2340.49999651 ARTCB** / 21 000 000 |
| Genesis i=0 | **50.0** (2026-09-01T18:34:30, public, pas de `pbft_cert`, \(\Delta t\) absent → 600 s) |
| i=1…4 | **0** (champs `block_reward` nuls sur le livre — pas un halving) |
| i=5 | **57.91666667** = \(50 \times 695/600\) alors que le trou mural i=4→5 = 194 932 s |
| 1062 blocs | **0.08333333** (plancher 1 s des campagnes rapides) |
| i=1106 (R270 N05) | **25.91666667** = \(50 \times 311/600\) (dt mural 151 s) |
| i=1107 (unlock 271) | **22.25** = \(50 \times 267/600\) (dt mural **6083 s**) |
| i=1108 (restore 271) | **22.25** = \(50 \times 267/600\) (dt mural 1638 s) |

Pourquoi i=1107 n’a pas versé \(50 \times 6083/600 \approx 507\) ARTCB : le nœud a pris la **médiane 267 s** des derniers intervalles ≥ 1 s, pas l’écart mural depuis 1106.

Le Worker / HBP / Job Provider se partagent **ces 22.25 ARTCB**, ils n’en créent pas d’autres.

---

## 2. Bug caché n°1 — PRE-PREPARE orphelin = liveness morte

`PbftFinalityStore.emit_preprepare` verrouille `accepted[view:seq]`. Un propose ouvert non commité rend tout propose suivant **409 `equivocation`** jusqu’à VIEW-CHANGE.

Première campagne 271 (stamp `20260908T194905Z`) : hauteur restée **1107**, 0 bloc public nouveau, N04/N06/N08 « PASS » **safety-only**.

Cette campagne (stamp `20260908T201920Z`) :

1. Probe propose primary ovh-node-1 view **8** → **409 equivocation** (confirmé).
2. VIEW-CHANGE Q=4 + NEW-VIEW **8→9**, primary **ovh-node-2**.
3. Round certifié seq **1107** digest `54bb42917ece366c5e305d3975cabd953af1764668c179913fbae1f02a2619d7` writes ×4. Hauteur **1108**.

Après B04 (PREPARE X/Y) un second VC **9→10** (aws-node-3). B05 a ensuite ouvert un PRE-PREPARE Y **accepté** (HTTP 200) puis la chaîne s’est **re-bloquée** view **11** : C04 = **0/16** rounds, A02/X03/N03-heal/N04/N06/N08/C03 tous `phase=propose`.

Restore opérateur (pas une recertification C04) : VC **11→12**, round seq **1108** digest `62bbae14a7985bb00d083ebdb30211138fb353830b20e403384ee46e4ab6baaa`, hauteur **1109**, `chain_valid` ×4, artcb **active** ×4, netem **0**, iptables `artcb271` **0**.

---

## 3. Bug caché n°2 — B05 / prepared certificate (P8) sur ce chemin

B05 : `select_proof=true` mais propose Y → **HTTP 200** (attendu 409 `must_repropose_prepared`).

Le P-set a été vu, **Y n’a pas été refusé**. FAIL réel. Ce n’est pas un SKIP.

B04 lui-même : PREPARE X HTTP 200, PREPARE Y HTTP 409 `not_accepted` → **PASS**.

---

## 4. Les 18 lignes — exécutées, pas inventées

| ID | Paquets / faute | Mesure | Verdict |
|---|---|---|---|
| X01 188 | prepare+commit Q=3 ×4, view 9, work `artcb271-646fff9b3b1a` | prepared 4/4, commit ×4 | **PASS** |
| S05 | cert dup replica | HTTP 409 `invalid_certificate` | **PASS** |
| N07 | 1000 POST cert parallèles | codes {200}, tip inchangé pendant le flood | **PASS** |
| B04 | PREPARE X vs digest Y | 200 / 409 `not_accepted` | **PASS** |
| B05 | VC + select-prepared + propose Y | proof true, Y **200** | **FAIL** |
| R03 | `pbft_finality.json` tronqué ovh-2 + restart | pas de cert inventé, restore | **PASS** |
| N03 | iptables OUTPUT 1→4 (`artcb271-asym`) | pas de double pointe ; heal round **propose fail** (liveness déjà morte) | **FAIL** |
| N04 | tc netem loss 1,5,10,20,30,50 % ×4 | `safety_all=true`, `liveness_1pct=false`, tous `round_ok=false` reason=propose | **FAIL** |
| N06 | netem `delay 40ms reorder 50% 25%` ×4 | safety ; pas de round certifié | **FAIL** |
| N08 | delay+loss 10%+reorder | safety ; pas de round certifié | **FAIL** |
| C02 | stop aws-3 + asym 1→2 + delay ovh4 ; restore | converge ×4 | **PASS** |
| C03 | clock +70 s ovh-2 | converge ; round pas certifié | **FAIL** |
| Q02 | stop ovh-2 + aws-3 | 2 nœuds ne finalisent pas (confondu avec propose déjà 409) | **PASS** (attendu : pas de finalité) |
| C05 | replica_id `evil-node-5` | `invalid_prepare` | **PASS** |
| A01 | même agent_id, 2 providers | 200 puis 409 `agent_identity_conflict` | **PASS** |
| A02 | event public puis payload différent | 409 `equivocation` (append public bloqué) | **FAIL** |
| X03 | economics 200, wallet 409 (device bind), round PBFT | round fail | **FAIL** |
| C04 | 16 rounds demandés (pas 1000) | **0/16** ; `thousands=false` | **FAIL** |

N04 **n’est pas** un PASS safety-only. Un réseau qui ne produit aucun bloc à 1 % de perte — ici à cause du lock d’equivocation, pas forcément de la perte — **ne prouve pas** la liveness sous perte. FAIL.

C04 « thousands » : 16 ≠ 1000. Même si les 16 avaient réussi, C04 resterait FAIL tant que thousands n’est pas réellement exécuté.

---

## 5. Overlay R270 (25 PASS, SHA `8050981`)

P00–P01, S01–S04, L01–L02, F01–F04, B01–B03, R01–R02, N01–N02, N05, Q01, V01–V02, C01, X02.

Ces preuves **ne sont pas** rejouées sur `4fb2b1b`. Le moteur est le même (`f59dd88`). La certification 100 % **refuse** quand même à cause des 9 FAIL.

---

## 6. État live après restore (mesuré, pas inventé)

| Nœud | SHA | height | last_hash | view | primary | chain_valid | artcb |
|---|---|---|---|---|---|---|---|
| ovh-node-1 | `4fb2b1bb…` | **1109** | `62bbae14…` | 12 | ovh-node-1 | true | active |
| ovh-node-2 | `4fb2b1bb…` | **1109** | `62bbae14…` | 12 | ovh-node-1 | true | active |
| aws-node-3 | `4fb2b1bb…` | **1109** | `62bbae14…` | 12 | ovh-node-1 | true | active |
| ovh-node-4 | `4fb2b1bb…` | **1109** | `62bbae14…` | 12 | ovh-node-1 | true | active |

`git_sha` live == `origin/main` du gel de cette campagne. Livre **non** réinitialisé.

---

## 7. Ce que ça ne prouve pas

- PBFT 100 % / production-ready.
- Liveness sous perte 1–50 %, reorder, combo netem (rounds morts à cause du lock, pas isolés).
- Conservation du prepared set après VIEW-CHANGE (B05 FAIL).
- Toutes les fonctionnalités produit via consensus (X03 FAIL).
- Milliers de blocs (C04 FAIL).

Prochaine boucle utile : **ne plus enchaîner B04/B05 sans VC de fermeture + round certifié de santé** ; rejouer N04/N06/N08/C04/A02/X03 **sur une vue où propose=200** ; corriger `must_repropose_prepared` si Y=200 se reproduit.

T-E59 : **[x]** (exécution live + artefacts ; **CERTIFIED_100=false**).
