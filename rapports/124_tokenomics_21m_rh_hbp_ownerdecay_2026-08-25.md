# Rapport 124 — Tokenomics 21 M cohérente + R(H) + HBP + OwnerDecay + settlement

**Date :** 2026-08-25  
**Branche :** `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**Base :** `main` (après merge rapport 123)  
**Avancement protocole économique : 100 %** de la couche demandée (émission 21 M, R(H), HBP, P_owner continu, binding, pré-blocs, Job Provider, settlement).  
**Avancement global système (hors TLS/libp2p natif étendu) : ~97 %**

Expertises mobilisées : audit Python / architecture blockchain, tokenomics, mechanism design, anti-Sybil / identité humaine, identité matérielle existante, scheduling pré-blocs, comptabilité des récompenses, simulation numérique.

---

## 1. Résumé

La simulation d’audit sur `main` était juste : le code **ne pouvait pas** distribuer 21 M ARTCB.

| | Code `main` avant | Modèle validé (intégré) |
|--|--|--|
| `R_0` | 1 ARTCB | **50 ARTCB** |
| Intervalle | 105 000 blocs | **210 000 blocs** |
| Asymptote réelle | `1 × 105_000 × 2 = 210_000` | `50 × 210_000 × 2 = 21_000_000` |
| Hard cap documenté | 21 000 000 (inatteignable) | 21 000 000 (calendrier cohérent) |

Couche **nouvelle** (n’existait pas dans le dépôt) :

- `R(H)` population, sans plancher à 1 ARTCB
- `HBP(H)` 10 % → 60 % → 20 %
- `P_owner(n)` **continu** (pas les paliers 50/40/30/20/10)
- Binding humain obligatoire pour la machine n≥2
- Pré-blocs : `∑ Reward(PB_i) = R_block`
- Job Provider + settlement owner / humain / HBP

Les deux index restent séparés : **H** = humains vérifiés réseau ; **n_A** = n-ième machine du propriétaire A.

---

## 2. Avant / après — fichiers sources

### 2.1 `src/artcb/tokenomics.py`

**Avant (L36–L43) :**

```python
INITIAL_BLOCK_REWARD_ARTCB    = 1.0
INITIAL_BLOCK_REWARD_SATOSHI  = int(INITIAL_BLOCK_REWARD_ARTCB * SATOSHI_PER_ARTCB)
HALVING_INTERVAL = 105_000
```

**Après (L40–L47) :**

```python
INITIAL_BLOCK_REWARD_ARTCB    = 50.0
INITIAL_BLOCK_REWARD_SATOSHI  = int(INITIAL_BLOCK_REWARD_ARTCB * SATOSHI_PER_ARTCB)
HALVING_INTERVAL = 210_000
```

`MAX_SUPPLY_ARTCB = 21_000_000.0` inchangé (L51–L56).  
`issued = min(schedule, R(H), remaining_21M)` — le halving dynamique (vitesse) reste une **soupape**, plus le seul régulateur.

### 2.2 `src/artcb/chain/manager.py`

**Avant (`_calculate_block_reward`) :** `INITIAL_BLOCK_REWARD_SATOSHI >> (epoch_fixe + epoch_dyn)` avec intervalle 105 k.

**Après (L364–L385) :** délégation à `issued_reward_satoshi(...)`.  
`append_block` accepte `verified_humans` et, si chaque contributeur porte `machine_index` + `owner_address`, applique `settle_block` (HBP + P_owner). Sinon : split PoL historique sur **100 %** de `R_block` (rétrocompat mining actuel).

Split PoL : `PolScorer.split_reward` alloue maintenant en satoshi entier (`allocate_satoshi`) — conservation exacte.

### 2.3 Nouveaux modules `src/artcb/economics/`

| Fichier | Rôle |
|---------|------|
| `emission.py` | Calendrier 50/210k + `R(H)` + hard cap |
| `hbp.py` | 10 % → 60 % @ 4,15e9 → 20 % @ 8,3e9 |
| `owner_decay.py` | P(1)=100 %, P(2)=50 %, τ/β calés sur 38 % @ 1k et 11,85 % @ 100k |
| `human_binding.py` | Registre machine, humain distinct obligatoire n≥2 |
| `preblocks.py` | Partition conservative |
| `job_provider.py` | submit → capacity → partition → settle |
| `settlement.py` | Owner / humain / HBP, `sum = R_block` |
| `satoshi.py` | Largest remainder — 0 création / 0 destruction |

### 2.4 API `src/api/economics_routes.py`

Préfixe `/api/v1/economics` : params, emission, hbp, owner-share, settle, preblocks, machines, jobs.

### 2.5 Genesis `scripts/init_genesis.py`

**Avant :** `"initial_block_reward": 1.0`, `"halving_interval": 105_000`, `genesis_version: 2.0`  
**Après :** `50.0`, `210_000`, `genesis_version: 3.0`

Les blocs déjà gravés **conservent** leur `block_reward` historique. Seuls les **nouveaux** blocs suivent D-023.

---

## 3. Preuves numériques (logs lus)

Fichiers :

- `logs/20260825_economics_protocol.json`
- `logs/20260825_pytest_economics.txt`

### 3.1 Identité 21 M

```
R0 × 210000 × 2 = 21000000.0
matches_21m = true
```

Poussière satoshi entier : le `>> k` laisse ~0,023 ARTCB non émis vs 21 M réels — **strictement sous** le hard cap (pas de dépassement). Documenté dans `test_asymptotic_schedule_hits_hard_cap`.

### 3.2 `R(H)` (simulation §8)

| H | Mesuré |
|--:|-------:|
| ≤ 1 M | 50,0000 |
| 10 M | 5,7323 |
| 64 M | 1,0000 |
| 100 M | 0,65718 |
| 1 Md | 0,07534 |

Pas de plancher à 1 ARTCB.

### 3.3 HBP

| H | HBP |
|--:|----:|
| 0 | 10,00 % |
| 100 M | 11,2048 % |
| 1 Md | 22,048 % |
| 4,15e9 | 60 % |
| 8,3e9 | 20 % |

À 1 Md : enveloppe HBP ≈ **0,01661 ARTCB/bloc** (log `hbp_pool_artcb: 0.01661173`).

### 3.4 `P_owner(n)` continu (plus de 50/50 figé sur A3)

| n | P_owner |
|--:|--------:|
| 1 | 100 % |
| 2 | 50 % |
| 3 | **49,948 %** (< P(2), ≠ 40 %) |
| 1 000 | 38 % (ancre exacte) |
| 10 000 | 20,06 % |
| 100 000 | 11,85 % (ancre exacte) |

Les paliers 50/40/30/20/10 de la première simulation **ne sont pas** le protocole. C’est la courbe continue de la seconde.

### 3.5 Settlement 100 M humains, R=50 (conservation)

HBP ≈ 11,2048 % → pool travail 44,3976 / 4 machines.

| Humain | ARTCB (continu) |
|--------|----------------:|
| A | 23,5937 |
| B | 6,9503 |
| C | 6,9560 |
| D | 12,5000 |
| **Total** | **50,0000** |

Écart vs table 40/60 de la 1re simulation : A et C, parce que A3 n’est plus 40/60. B et D inchangés (A2 reste 50/50 ; D1 reste 100 %). **Aucune création monétaire.**

### 3.6 Supply calendrier 600 s/bloc (H ≤ 1 M)

| Horizon | Supply |
|--------:|-------:|
| 1 an | 2 629 800 |
| 5 ans | 11 824 500 |
| 10 ans | 17 074 500 |
| 20 ans | 20 346 750 |
| 100 ans | ≈ 21 000 000 |

---

## 4. Tests (PROTOCOLE)

Commande : `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line`

```
535 passed, 20 skipped in 184.70s (0:03:04)
```

0 échec. Skips : bridges live + absence `liboqs` dans cet environnement (fallback Ed25519 déjà prévu).  
Nouveaux : `tests/test_economics_protocol.py`.  
Alignés 50/210k : `tests/test_wallet_rewards.py`, `tests/test_dashboard_api.py`.

Cibles LISTE_TESTS T-E01, T-E02, T-E03 : **passées**.

---

## 5. Ce que le dépôt savait déjà faire (inchangé)

Wallet, PoL, `contributors[]`, `PolScorer.split_reward`, Anti-Sybil, TPM/hardware identity, bridges BTC/ETH/SOL/BNB/Polygon/AVAX → `ir_text`.

## 6. Limites honnêtes

1. Le mining pipeline **n’attache pas encore** `machine_index` / `bound_human` aux contributeurs : sans ces champs, le split reste 100 % PoL (pas de HBP). L’API `/economics/settle` et `append_block(..., machine_*)` activent la couche complète.
2. `H` réseau n’est pas encore un compteur on-chain global : passé explicitement (`verified_humans`) ou 0 → `R(H)=50`, `HBP=10 %`.
3. Chaînes déjà minées à 1 ARTCB/bloc : historique conservé ; genesis v3.0 pour les **nouveaux** nœuds.
4. Job Provider ne paie pas encore automatiquement B on-chain (comptabilité + partition : oui ; virement wallet : via settlement au `append_block`).
5. Frontend : fallbacks d’affichage 1 ₳ → 50 ₳ (`ChainPage.tsx`) ; pas de nouvelle vue HBP (hors périmètre UI de cette passe).

---

## 7. Décision

**D-023** actée dans `DECISIONS_UTILISATEUR_ARTCB` : 21 M + 50 + 210 k + R(H) + HBP + P_owner continu + binding + pré-blocs conservatifs + Job Provider.

D-014 (21 M) et D-016 (210 000 blocs) sont **restaurés**. La révision 1/105k des rapports 045/080 est **obsolète** pour le protocole vivant.
