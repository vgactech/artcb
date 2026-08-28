# Rapport 163 — Simulations 162 + alignement code (D-025)

**Horodatage UTC :** 2026-08-28T18:10:00Z  
**Branche :** `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**HEAD au moment de ce fichier :** `df2c0b5` (code) + commit suivant (ce rapport + docs protocole)  
**Dump lu en entier :** `rapports/162 conversation chat et simulation artcb.md` (12 928 lignes, ordre conversationnel reconstitué)  
**Simulations :** `simulations/20260828T174810Z_rapport162/`  
**Pytest :** `logs/20260828_pytest_rapport163.txt` — **554 passed, 20 skipped, 0 fail**  
**Langue :** rapport FR, code EN. Aucun mock économique.

**Expertises mobilisées :** tokenomics / mechanism design, identité Finder, settlement multi-rôles, consensus hash (EconomicRoot), frais + dividende, liveness machines.

**Avancement de cette passe**

| Volet | % | Note |
|-------|---|------|
| Lecture 162 ligne à ligne + reconstitution ordre | **100 %** | dump ChatGPT désordonné |
| Simulations demandées par 162 (émission, OwnerDecay, HBP/Finder, WorkID, P/W, root, frais/vault/lock, identité, MC 2000) | **100 %** | 0 fail simu |
| Décisions GO 162 enregistrées (D-025) | **100 %** des points tranchés |
| Code economics aligné 162 | **~88 %** | modules + chain + API params |
| Finder/HumanID/WorkID **branchés mining/API complète** | **~35 %** | modules réels, pas encore pipeline |
| Oracle frais USD→ARTCB consensus | **0 % live** | quote USD + cap observé seulement |
| Hash C natif `EconomicRoot` | **workaround Python** | mix merkle, pas de fork ABI C |
| **Global cette passe vs 162** | **~82 %** | reste câblage mining + oracle + WPP daté |

Ne **jamais** écraser 160, 161, 162.

---

## 1. Ordre conversationnel de 162 (dump ChatGPT)

Timestamps utilisateur dans le fichier (pas l’ordre d’affichage ChatGPT) :

1. **Hier 02:12 / 12:32** — « mets-toi à jour / relance simu » (ChatGPT encore sur `c7c6915`).
2. **Hier 21:41** — gros GO : M1 100 % pour toujours, binding propre + 1 externe, N_A peut baisser, partition hash, PB manquant requeue, jobs on-chain, lock 30 j, biométrie recovery, EconomicRoot, etc.
3. **Aujourd’hui 00:34** — Monte Carlo.
4. **Aujourd’hui 16:57** — relance + Q=100 creator-direct, GRACE, 50/50 Provider/Worker, émission vs fréquence, frais oracle, audit binaire, « tout ce que je n’ai pas cité » de **cette** passe ChatGPT.

Les suggestions ChatGPT **ne sont pas** D-xxx. Seuls les GO utilisateur (et la phrase de validation de **cette** passe) sont actés. Constantes magiques non fournies → paramètre documenté, pas gel.

---

## 2. Conflits documentaires (162 gagne)

| Sujet | Avant | 162 + dernier GO | Action |
|-------|--------|------------------|--------|
| Frais collectés | D-024 / 161 : → RemainingSupply | **UniversalDividendVault** séparé | D-025 amende D-024 sur ce point |
| OwnerDecay | par **index** machine, 38 % @ 1000 | **M1=100 % toujours** ; extras **même P(N_economic)** | code live remplacé |
| Émission vs vitesse | `min(R(H), remaining)` par bloc, indépendant du dt | 10× plus de blocs ⇒ **1/10** reward/bloc | `R(H)×dt/T`, T=600 s déjà §4.1 |
| Halving 210k | retiré D-024 | **confirmé retiré** | pas réintroduit |

---

## 3. Simulations (lues en entier après chaque run)

Dossier : `simulations/20260828T174810Z_rapport162/`  
README des runs : ce dossier + copie `logs/20260828_sim_rapport162_README.md`  
DEBUG stdout : `simulations/20260828T174810Z_rapport162/run.log` (copie `logs/20260828_sim_rapport162_run.log`)  
Manifest : `out/00_manifest.json` — **failures: []**

### 3.1 Preuves numériques (pas de mock)

**Émission (`out/01_emission.json`)**

- Index 0 et 210 000 : **même** R(H) (H=0→50 ; H=1e9→0,07534283). Le 210k **ne coupe plus**.
- Naive 50 ARTCB/bloc @ 10 s → **48,61 jours** jusqu’à 21 M.
- Time-norm `R×dt/600` : **2 916,67 jours ≈ 7,985 ans** à H≤1 M, **identique** à 600 s / 60 s / 10 s / 1 s.
- `extra_epochs_ignored: true`. Dernier bloc clipé à 1 satoshi.

**OwnerDecay (`out/02_owner_decay.json`)** — sim 162 vs live **avant** patch :

| N | Live index (ancien) | Fleet 162 | Exemple user |
|---|---------------------|-----------|--------------|
| 1 | 100 % | M1=100 % | — |
| 2 | 50 % | 50 % | 50 % |
| 3 | 49,95 % | **49,00 %** | 49 % |
| 4 | 49,91 % | **48,025 %** | ~48 % |
| 1000 | **38 %** | **10,0000000004 %** | floor |

k dérivé (pas inventé) : `k = -ln(0.975) = 0,025317807984` pour P(3)=49 % exact.  
Offline 8/10 : N_economic=10, P extras=42,67 % ≠ 50 % si on comptait seulement l’online.

**HBP / Finder (`out/03_hbp_finder.json`)**

- Trajectoire 10→60→20 **dans** l’enveloppe ; somme HBP+work = R(H).
- Finders @ 25/j : **764 056** vs 70 184 @ 272,16/j (ratio ≈ 10,89). 272,16 **écarté**.

**WorkID / partition (`out/04_workid_partition.json`)**

- `SHA256(WorkID\|Epoch\|ParentRoot) mod 5` sur 10 000 WorkID : 1962 / 1954 / 2013 / 1999 / 2072, déterministe.
- Double settlement W-00001 → `REJECT_DOUBLE_SETTLEMENT`.
- PB3 manquant : bloc continue, 4e9 satoshi présents sur 5e9, reliquat requeue, conservation ≤ R_block.

**Provider/Worker (`out/05_provider_worker.json`)** : 50/50 départ, pools 2e9+2e9=4e9. Bornes 20–80 = **paramètre**. Job externe ≠ mint.

**Settlement + root (`out/06_settlement_economic_root.json`)** : conservation 5e9 ; A2 et A3 **même P=49 %** dans 162 (live ancien A2=50 %, A3=49,95 %). EconomicRoot change si settlement muté.

**Frais / vault / lock (`out/07_fees_dividend_lock.json`)** : congestion 1000 → quote **plafonnée à 0,000311 USD** (OpenChainBench Base p50 2026-08-26). Fiat 1 € exemple processor 0,265 → 0,735 vault, **ne mint pas**. Lock 30 j après finalité mensuelle.

**Identité (`out/08_identity_machines.json`)** : Q=100, creator-direct, 2e binding externe **rejeté**. Biométrie brute jamais on-chain.

**Monte Carlo (`out/09_monte_carlo.json`)** seed=42, 2000 runs × 12 mois :

| Invariant | Violations |
|-----------|------------|
| supply ≤ 21 M | **0** |
| M1=100 % | **0** |
| offline shrink | **0** |
| binding | **8** (tentatives 2e binding **détectées puis clampées**, pas un fail protocole) |
| WorkID / PB / root / lock / mint externe | **0** |

issued_min = issued_median = **2 592 000** ARTCB / an de simu (budget temps-normé). `issued_always_le_21M: true`.

**Inventaire pré-code (`out/10_code_gap_inventory.json`)** : photographie **avant** implémentation (beaucoup de GAP). Ne pas le lire comme l’état final.

**Vérif post-impl (`out/11_post_impl_live.json`)** 2026-08-28T17:59:00Z :

- `index_210k_does_not_cut: true`
- `time_norm_10s_is_1_60: true` (50/60)
- M1 @ N=1e6 = **1.0**
- fleet P(3)=0,49 ; P(4)=0,48025 ; P(1000)≈0,10 (plus 38 %)
- settlement A2 owner satoshi **=** A3 owner = 543 870 482 ; conservation true

---

## 4. Inventaire 162 vs code (après implémentation)

| Demande 162 | Module | Statut |
|-------------|--------|--------|
| `min(R(H), remaining)` + pas de 210k | `emission.py` | **DONE** D-024, conservé |
| Time-norm `R(H)×dt/T` | `emission.py` + `ChainManager._last_observed_interval_seconds` | **DONE** (filtre burst <1 s pour tests labo) |
| H = adultes 18+ | `identity.ADULT_AGE_YEARS=18` | **DONE naming** ; compteur mining encore `verified_humans` |
| DemographicReference modèle B | `demographic.py` | **DONE structure** ; WPP daté **non gelé** |
| HBP 10→60→20 | `hbp.py` | **DONE** ; ancres 4,15e9/8,3e9 **provisoires** |
| HBP pondéré | `settlement.py` `hbp_scores` | **DONE** (équiparti si scores absents) |
| M1=100 % toujours | `payout_owner_share` | **DONE** |
| M2+ même P(N_economic) | `fleet_owner_share` | **DONE** |
| Offline ≠ retiré | états GRACE/OFFLINE dans `ECONOMIC_STATES` | **DONE** |
| Binding externe ≤1 | `external_bindings_of` | **DONE** |
| N_A baisse après transfer/retire | `transfer` / `finalize_retire` | **DONE** ; délai retire **non figé** |
| WorkID unique | `workid.py` | **DONE module** ; pas encore mining |
| Partition hash mod N | `partition_map.py` | **DONE module** |
| PB manquant requeue | `requeue_missing_preblock` | **DONE module** |
| N_max dynamique | `network_capacity.py` | **DONE** (safety 0,75 = paramètre) |
| Provider/Worker 50/50 | `provider_worker.py` | **DONE** ; sans providers → 100 % workers (compat mining) |
| Jobs on-chain, fiat = priorité | `dividend.credit_fiat_net` | **DONE spec** ; Stripe **pas** constante |
| UniversalDividendVault | `dividend.py` | **DONE** |
| Frais ARTCB, cap min L2 observé | `fees.py` | **DONE USD** ; oracle prix **ouvert** |
| Lock 30 j | `monthly_lock.py` | **DONE** |
| EconomicRoot dans BlockHash | mix merkle Python | **DONE workaround** ; C ABI inchangé |
| Audit binaire append-only | `audit_log.py` | **DONE module** |
| Finder Q=100 + creator-direct + revalidation | `identity.py` | **DONE module** ; pas API mining |
| PoLRecord ; tokens LLM ≠ preuve | `pol_record.py` + `pol_from_useful_work` | **DONE** |
| 0,4 C + 0,3 V + 0,3 R | exemple user, utilisé comme **exemple** | documenté, pas D-xxx gelé |

---

## 5. Avant / après (fichiers + lignes)

### 5.1 `src/artcb/economics/emission.py`

**Avant (D-024, `c7c6915`)** : `issued = min(R(H), remaining)` sans dt.

**Après** lignes 70–123 : `scaled = r_h * (interval / TARGET_BLOCK_SECONDS)` puis `min(scaled, remaining)`. `block_index` toujours inutilisé pour une coupe. `extra_epochs` toujours ignoré.

### 5.2 `src/artcb/economics/owner_decay.py`

**Avant** : `P_owner(n)` par **index**, τ/β calés 38 % @ 1000.

**Après** lignes 41–50 : `P(N)=0.10+0.40*exp(-k*(N-2))` pour **tous** les extras ; M1 via `payout_owner_share` = 1.0. Ancien 38 % archivé `LEGACY_CALIB_*`, non live.

### 5.3 `src/artcb/economics/settlement.py`

**Avant** : HBP équiparti ; P_owner(index) différent A2 vs A3.

**Après** lignes 1–13 + 142–160 : M1 100 % ; extras `payout_owner_share(..., n_economic)` **identique** ; HBP pondéré optionnel ; split P/W si `provider_scores`.

### 5.4 `src/artcb/chain/manager.py`

**Après** lignes 265–270, 309–321, 395–425 : intervalle médian (ignore <1 s) ; `economic_root` mixé dans `merkle` **avant** `ffi.build_block_hash` (pas de fork C).

### 5.5 `src/artcb/tokenomics.py`

`TARGET_BLOCK_SECONDS = 600.0` (déjà TOKENOMICS §4.1). `EMISSION_MODEL = "R(H)"`. Frais → vault (D-025), plus remaining.

### 5.6 Nouveaux fichiers

`audit_log.py`, `demographic.py`, `dividend.py`, `economic_root.py`, `fees.py`, `identity.py`, `monthly_lock.py`, `network_capacity.py`, `partition_map.py`, `pol_record.py`, `provider_worker.py`, `workid.py`  
Tests : `tests/test_economics_rapport162.py`

---

## 6. Erreurs / fails en cours de route + correctifs

| # | Symptôme | Cause | Correctif |
|---|----------|--------|-----------|
| 1 | 1er pytest : **32 failed** | Environnement : pas de `libartcb_chain.so` (OpenSSL headers absents), pas de pytest/faiss au boot | `apt libssl-dev` + `make -C src/c` + pip pytest/fastapi/faiss. **Pas une régression 162.** |
| 2 | `test_strictly_decreasing_after_two` `assert 0.1 < 0.1` | Nouvelle courbe touche le plancher dès n≈1000 | Test : décroissance stricte jusqu’à n=200, puis floor @ 10k/100k |
| 3 | `pol_from_useful_work() takes 0 positional arguments but 1` | Méthode d’instance sans `self` | `@staticmethod` |
| 4 | Burst tests 2e bloc ≈ 0 reward | dt réel <1 s × time-norm | Filtre mesure ≥1 s, sinon T=600 s (filtre labo, **pas** calendrier 210k) |
| 5 | Mining sans providers aurait pris 50 % « dans le vide » | 50/50 strict | Si `provider_scores` vide → 100 % workers (legacy 50 ARTCB) |

Simulations 162 : **0 fail**. Pytest final : **0 fail**.

---

## 7. Ce que l’utilisateur a oublié de préciser (comblé sans magie contradictoire)

1. **k OwnerDecay** — dérivé de P(3)=49 % ; P(4) tombe à 48,025 % (exemple ~48 %). Si tu veux P(4)=48 % **exact**, il faudra une autre famille de courbe (question).
2. **T=600 s** — déjà dans TOKENOMICS §4.1 ; pas une constante nouvelle.
3. **Cap frais USD** — observé Base p50 0,000311 (2026-08-26). Pas un montant ARTCB. Spark « free » exclu.
4. **Floor anti-spam 1e-6 USD** — ordre de grandeur, **paramètre**.
5. **Bornes P/W 20–80 %** — suggestion ChatGPT, **paramètre**.
6. **Safety N_max 0,75** — paramètre.
7. **Délai de retraite / transfer pending** — non figé (jours ? epoch ?).
8. **Oracle ARTCB/USD** — obligatoire pour convertir le cap ; pas encore consensus.
9. **HBP à H=0** — toujours 10 % de R aux humains **présents** (créateur bootstrap). Pas burn. Q-E04 encore discutable si « aucun humain ».
10. **Mining sans Job Provider** — 100 % PoL aux workers pour ne pas casser le split historique.
11. **Filtre dt<1 s** — pour ne pas vider les tests CPU ; une vraie chaîne 10 s **scale**.
12. **âge adulte 18 universel** — proposé et codé comme constante protocole ; pas de table par pays.

---

## 8. Questions encore ouvertes

| ID | Question |
|----|----------|
| Q-E03 | Extraction ONU WPP **18+ datée** + hash dataset pour geler `H_adult,max` (5,82e9 reste estimation ; modèle B prêt) |
| Q-HBP-ancres | Recaler 4,15e9 / 8,3e9 une fois WPP 18+ connu |
| Q-E04 | HBP si **zéro** humain vérifié dans le bloc (aujourd’hui : erreur si pool>0 et liste vide) |
| Q-k | Recaler k pour P(4)=48,000 % exact, ou garder l’exponentielle P(3)=49 % |
| Q-PW-bounds | Figer 20–80 % ou autre |
| Q-retire | Délai TRANSFER_PENDING / RETIRED |
| Q-fee-oracle | Snapshot FeeOracle + prix ARTCB (gouvernance) |
| Q-Finder-delay | 0 / 7 / 30 j avant qu’un VERIFIED puisse finder |
| Q-revalid | Échec de revalidation creator-direct : slash, timeout, rétrogradation ? |
| Q-geo | Diversité géographique des 100 Finders |
| Q-wire | GO pour brancher `HumanRegistry` / `WorkRegistry` / audit log sur `/mining/pipeline` et l’API |
| Q-C-ABI | Fork `build_block_hash` C pour EconomicRoot natif (aujourd’hui mix merkle Python) |
| Q-E12 | 1 wallet/device rapport 114 vs règle 162 « machine propre + 1 binding externe » (on a implémenté 162) |

**Fermées par 162 / D-025 :** Q-E02 (M1=100 % toujours), Q-E05 (HBP pondéré si scores), Q-E06 (50/50 départ), Q-E08 (courbe fleet, plus 38 %@1k), Q-E09 (1 binding externe ; N_A peut baisser), Q-E10 partiel (modules Finder/WorkID, pas encore mining).

---

## 9. Pytest

Commande : `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line`  
Log : `logs/20260828_pytest_rapport163.txt`

**Résultat final :** 554 passed, 20 skipped, 1 warning (Starlette/httpx TestClient).  
Skipped = PQC liboqs / chemins optionnels (préexistant).  
1er run environnement : 32 failed (`.so` + faiss + 2 vrais bugs 162) — tous corrigés ou outillés.

---

## 10. Git / PR

Branche uniquement `cursor/tokenomics-21m-hbp-owner-decay-3fcb`. Pas de merge `main`.  
Compare : https://github.com/vgactech/artcb/compare/main...cursor/tokenomics-21m-hbp-owner-decay-3fcb  

Outil ManagePullRequest **absent** de cette session (pas collaborateur write PR via API dédiée). Créer/MAJ la PR à la main si besoin.

---

**Fin rapport 163.**
