# PBFT certification finale — 2026-09-08

**Verdict global : 🟠 PBFT PARTIELLEMENT VALIDÉ**

```text
CERTIFIED_100 = false
FAIL = 0
PASS (lignes exécutées) = 25
NOT_PROVEN = 18
TOTAL_REQUIRED = 43
```

**PBFT 100 % CERTIFIÉ : NON.**  
Une propriété critique non exécutée live suffit. Ici : perte de paquets, réordonnancement, partition asymétrique, long-run, membership, PREPARE sélectif multi-nœuds, settlement 188, couverture fonctionnelle ARTCB, etc.

Ce n’est **pas** « 25/43 = 58 % de sécurité ». Ce n’est **pas** non plus le 100 % PASS de la campagne interne R269 P9–P18 (autre objet).

AWS : **t3.small** `i-085b74abd1aaf04ee`. HPC : **false**. Wipe : **false**.

---

## 1. Gel cryptographique

| Champ | Valeur mesurée |
|---|---|
| SHA live ×4 | `805098126cf3f6dd5ef614b44ba59899a4e53e72` = `origin/main` au gel |
| Moteur PBFT | `f59dd88dfacde1a898fd59b01040a02a59f7e3b2` (parent docs-only de `8050981`) |
| Runner agent | `9ddc46500b03e02b171337a023aa8e90882c2e7b` (matrice ; pas déployé pendant le run) |
| N, F, Q | **4, 1, 3** (`n_f_q(4)`, `Q=2F+1`) |
| genesis_hash | `genesis-artcb-mainnet-1` |
| network_id | `artcb-mainnet-1` |
| protocol_version | `189-mainnet-1` |
| PQC déclaré | ML-DSA-65 ; Ed25519 encore accepté (`ed25519_only_still_accepted=true`) |
| Replicas | ovh-node-1, ovh-node-2, aws-node-3, ovh-node-4 |
| Hauteur gel | **1101** tip `204f6164123bd65c…` view **7** primary **ovh-node-4** |
| Après campagne | **1107** tip `94f57bb2a74e98b0…` view **8** primary **ovh-node-1** `chain_valid` ×4 |

JSON brut : `logs/270_pbft_cert_20260908T182742Z.json`.

---

## 2. Settlement BFT vs block consensus

| Verdict | Statut |
|---|---|
| `BFT_SETTLEMENT` (188 prepare/commit WorkID) | **NOT_PROVEN** sur ce SHA (non rejoué) |
| `BFT_BLOCK_CONSENSUS` (265 exclusive public append) | **PARTIELLEMENT VALIDÉ** : `run_round` ×2 seq 1101 `482ab4d6…` et 1102 `1e7c9f31…` writes ×4 ; public dès seq **1087** exige un certificat |
| Global | **PARTIELLEMENT VALIDÉ** |

Les mémos **privés** ne sont pas du PBFT public. Le bloc 1100 R269 n’avait pas de `pbft_cert`.

---

## 3. Table de certification (extrait obligatoire)

| ID | Propriété | Test live | Résultat | Niveau | Verdict |
|---|---|---|---|---|---|
| PBFT-S01 | Safety (pas deux finalités incompatibles) | Oui, scénarios exécutés | aucun dual tip observé | L4 ≠ L6 exigé | **PASS observé / NOT L6 exhaustif** |
| PBFT-S02 | Finalité | attente idle, pas coupure WAN totale | tip inchangé `1e7c9f31…` | L4 | PASS partiel |
| PBFT-L01 | Liveness | 2 rounds certifiés ×4 | PASS | L4 | PASS |
| PBFT-L02 | Liveness après primary down | view 7→8 seq 1105 | PASS | L5 | PASS |
| PBFT-F01/F04 | Crash/restart | ovh-node-1 stop/start | PASS | L5 | PASS |
| PBFT-F02 | Primary down + nouveau bloc | ovh-node-4 OFF ; majority certify seq **1105** `eb58e40d…` | PASS | L5 | PASS |
| PBFT-F03 | Rejoin | `p2p/replica/run` puis height 1107 ×4 | PASS | L5 | PASS |
| PBFT-B01 | Equivocation | 200 puis 409 `equivocation` | PASS | L6 | PASS (HTTP primary) |
| PBFT-B02 | PREPARE Y | 409 `not_accepted` | PASS | L6 | PASS |
| PBFT-B03 | Signature forgée | PREPARE `signature=00` rejeté | PASS | L6 | PASS |
| PBFT-B04 | Votes contradictoires sélectifs | — | — | L0 | **NOT_PROVEN** |
| PBFT-N01 | Partition 2–2 | left_ok=false right_ok=false dual=false | PASS | L5 | PASS |
| PBFT-N02 | Heal | convergence ×4 | PASS | L5 | PASS |
| PBFT-N03 | Partition asymétrique | — | — | L0 | **NOT_PROVEN** |
| PBFT-N04 | Perte 1–50 % | — | — | L0 | **NOT_PROVEN** |
| PBFT-N05 | Délai 100 ms `ens3` ovh-2 | seq 1106 `94f57bb2…` | PASS | L5 | PASS (un point, pas jitter) |
| PBFT-N06 | Réordonnancement | — | — | L0 | **NOT_PROVEN** |
| PBFT-N07 | Duplication 1000× | 20× cert seulement | — | L4 | **NOT_PROVEN** |
| PBFT-Q01 | Q<3 | 2 nœuds `primary_not_in_set` | PASS faible | L4 | PASS (preuve 2–2 N01 plus forte) |
| PBFT-V01 | VIEW-CHANGE | VC×3 NEW-VIEW view **8** primary ovh-node-1 | PASS | L5 | PASS |
| PBFT-V02 | Replay mauvaise view | 409 `invalid_preprepare` | PASS | L4 | PASS |
| PBFT-C01 | Byzantine + crash | ovh-2 down ; X 200 Y 409 ; seq **1104** `3cfe2e44…` ; replica | PASS | L6 | PASS (une combinaison) |
| PBFT-C02…C05 | Combinaisons / long-run / membership | — | — | L0 | **NOT_PROVEN** |
| PBFT-X01 | Settlement 188 | — | — | L0 | **NOT_PROVEN** |
| PBFT-X03 | Toutes features ARTCB via consensus | — | — | L0 | **NOT_PROVEN** |

Lignes complètes : `logs/PBFT_CERTIFICATION_FINAL_latest.json`.

---

## 4. Ce que le run a réellement fait (pas le rapport seul)

1. Deux hauteurs publiques certifiées (1101, 1102) sur 4 nœuds.
2. Equivocation + PREPARE Y + replay + cert≠bloc + 20 duplicatas.
3. Crash d’un replica puis restore.
4. Replica down **et** equivocation **et** certificat majority seq 1104 **et** rattrapage **protocole** (`replica/run`, pas jsonl-append).
5. Partition iptables 2–2 réelle : **aucune** finalité de côté ; restore ; convergence.
6. Arrêt réel du primary ovh-node-4 ; VIEW-CHANGE Q=3 ; NEW-VIEW 8 ; bloc seq 1105 ; redémarrage ; replica.
7. `tc netem delay 100ms` sur ovh-node-2 `ens3` puis restore ; seq 1106.

Processus **active** ×4 après coup. iptables artcb266 = 0. Pas de qdisc netem résiduelle.

---

## 5. Q1–Q20 (obligatoires)

| Q | Question | Réponse |
|---|---|---|
| Q1 | Même protocole ×4 ? | **OUI** `8050981` |
| Q2 | Production de blocs réellement BFT ? | **PARTIEL** public exclusif PBFT ; privé hors certificat ; 188 non rejoué |
| Q3 | Safety démontrée ? | **PARTIEL** (scénarios exécutés, pas toutes les classes) |
| Q4 | Liveness démontrée ? | **PARTIEL** |
| Q5 | Finalité démontrée ? | **PARTIEL** (idle, pas isolation WAN totale) |
| Q6 | Failover réel ? | **OUI** sur ce SHA (primary kill + nouveau bloc) |
| Q7 | View-change réel ? | **OUI** 7→8 VC×3 |
| Q8 | Partition réelle ? | **OUI** 2–2 |
| Q9 | Rejoin réel ? | **OUI** `replica/run` |
| Q10 | Fork distribué réel ? | **PARTIEL** (2–2 n’a pas produit FINAL_A+FINAL_B ; pas deux primaries concurrents WAN) |
| Q11 | Equivocation Byzantine ? | **OUI** HTTP |
| Q12 | Signatures forgées rejetées ? | **OUI** |
| Q13 | Replay rejetés ? | **OUI** |
| Q14 | Duplications ? | **PARTIEL** (20×, pas 1000×) |
| Q15 | Messages réordonnés ? | **NON — NOT_PROVEN** |
| Q16 | Pertes et retards ? | **PARTIEL** (100 ms oui ; perte 1–50 % non) |
| Q17 | Crash/restart ? | **OUI** |
| Q18 | Persistance cohérente ? | **PARTIEL** (restart oui ; JSON tronqué non rejoué ici) |
| Q19 | Toutes features ARTCB via consensus live ? | **NON — NOT_PROVEN** |
| Q20 | Une propriété critique non testée ? | **OUI** |

Donc :

# PBFT 100 % = NON CERTIFIÉ

---

## 6. Fonctionnalités ARTCB vs consensus

| Fonction | Live via PBFT cette campagne |
|---|---|
| Append public certifié | OUI (rounds 270) |
| Mémo privé | hors certificat (R269) |
| Wallets / paiements / PoL / HBP / ORG / gouvernance | **NOT_PROVEN** |
| Agent identity / idempotence | R269 sur `f59dd88`, **non rejoué** ici → NOT_PROVEN pour ce gel |
| Ingest universel IA | **non** (`ingest_platform_hook=false`) |

---

## 7. Limites assumées

- Runner = opérateur SSH/root ≠ attaquant HTTP distant pour crash, iptables, tc, replica.
- Q01 « 2 nœuds » a échoué par `primary_not_in_set` (preuve faible) ; N01 2–2 est la preuve quorum.
- S01 n’atteint pas L6 « toutes combinaisons Byzantine ».
- Preuves R268/R269 sur d’autres SHA **non recyclées** comme certification de `8050981` sauf le moteur inchangé `f59dd88` pour le code ; les scénarios non rejoués restent NOT_PROVEN.

Artefacts : `logs/270_pbft_cert_latest.json`, `rapports/PBFT_CERTIFICATION_FINAL_20260908.json`.
