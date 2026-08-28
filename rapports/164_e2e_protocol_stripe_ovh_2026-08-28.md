# Rapport 164 — Intégration e2e du protocole (Simulation 164)

**Horodatage UTC :** 2026-08-28T19:55:44Z  
**Branche :** `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**HEAD code (déjà poussé) :** `4debc5d3184e31ced1c69661d389628ea1b3de1b`  
**HEAD de ce rapport :** *(estampillé après le commit docs 164)*  
**Simulations :** `simulations/20260828T194555Z_e2e164/`  
**Pytest :** `logs/20260828_pytest_rapport164.txt`  
**Langue :** rapport FR, code EN. DEBUG ON. Aucun mock économique.  
**Ne jamais écraser** les rapports 160, 161, 162, 163.

**Cette passe n’est pas « protocole terminé ».** Les modules 162/163 existaient (~82 %). Le trou était le câblage d’une **seule exécution** :

```
HumanID → MachineID → WalletID → HumanBinding → JobID/WorkID
→ Capacity → Partition → PB → PoL → Provider/Worker → HBP
→ OwnerDecay → EconomicRoot → BlockHash → Settlement → soldes
```

---

## Avancement honnête (164 vs 163)

| Volet | 163 | 164 | Note |
|-------|-----|-----|------|
| Modules economics isolés | ~88 % | ~92 % | JobPayment, oracle, ProtocolEngine |
| **Intégration e2e mining/API** | **~35 %** | **~70 %** | `ProtocolEngine` + contributors identity ; sans machines → PoL héritage |
| Oracle USD→ARTCB | 0 % live | **~40 %** | Probe HTTP réel ; ticker ARTCB **absent** → stub `live=False` (pas de prix inventé) |
| Hash C `EconomicRoot` | workaround Python | **~95 %** | ABI v2 native + v1 inchangé |
| Stripe JobPayment | 0 % | **GHA success (secret injecté)** | Local skip ; GHA run 33206660774 = 6 passed, jamais loggé |
| OVH = cette branche | non prouvé | **non** | Health 200, economics **404** |
| **Global vs 162** | ~82 % | **~78 % du protocole réel** | Plus d’intégration, moins de « modules seuls ». Pas fini. |

Le chiffre global **baisse** volontairement vs 82 % : 163 mesurait « modules écrits ». 164 mesure « une exécution unique liée ». C’est plus strict, et c’est le trou identifié par l’audit.

---

## 1. Ce qui a été câblé

### 1.1 Simulation 164

Dossier : `simulations/20260828T194555Z_e2e164/`  
DEBUG : `run.log` (copie `logs/20260828_sim_e2e164_run.log`)  
Moteur : `src/artcb/mining/protocol.py` (`ProtocolEngine`) — **vrai code**, pas un jumeau fictif.

Acteurs : A, B, C, D puis E.  
Machines : A→M1 ; A→M2→B ; A→M3→C ; A→M4→D ; puis A→M5→E.

| Preuve | Valeur |
|--------|--------|
| `failures` | `[]` |
| Conservation Σ paiements = budget | **true** (tous les blocs) |
| Supply ≤ 21 M | **true** (340 ARTCB émis dans la simu) |
| P(N) N=4 → N=5 | 48,025 % → 47,074 % (`p_changed: true`) |
| H_adult live | 5 (registry 18+) |
| Hash ABI | v2 native `c_economic_root_abi: true` |
| JobPayment ≠ R_block | `stripe_mints: false` |

Jobs : small, large, simultanés, **cancelled**, **partial**.  
Réseau : low / medium / high + plus de pre-blocks + PB manquant (`pb3`) + requeue + reprise après offline.

### 1.2 Attaques (doivent REJECT)

| # | Attaque | Résultat |
|---|---------|----------|
| 1 | Double binding A : M2→B et autre machine→B | **REJECT** `already bound` |
| 2 | Double settlement même WorkID `W-m5` | **REJECT_DOUBLE_SETTLEMENT** |
| 3 | Owner A coupe le paiement de B | **IMPOSSIBLE** + `REJECT_OWNER_CUT_PAYMENT` |
| 4 | M2 ACTIVE→GRACE→OFFLINE | N_A **inchangé** (5→5) |
| 5 | Transfer M2 vers Z | N_A 5→4, P recalculé 47,07 % → 48,03 % |
| 6 | Fake human (même adresse / même HumanID) | **FAKE_HUMAN** + déjà enregistré |
| 7 | Tamper EconomicRoot | root **et** BlockHash changent ; chaîne live toujours valide |

### 1.3 Mining / API (~70 %, pas 100 %)

- Contributors : `machine_index`, `owner_address`, `human_id`, `work_id`, `bound_human_address`, `n_economic`.
- `MiningPipeline.bind_identity` + `ChainManager.bind_identity`.
- `H_adult` = `HumanRegistry.verified_adult_count()` si pas d’override.
- Settlement économique **si** tous les contributors portent `machine_index` + `owner_address` ; sinon PoL héritage.
- API : `/api/v1/mining/protocol`, `/api/v1/economics/humans`, `/workids`, `/h-adult`, `/oracle`, `/jobs/priority`.
- `/store` et AI routes passent les registries.

**Encore ouvert :** un nœud OVH / un user qui mine **sans** machines enregistrées reste en split PoL 50/50 héritage. Les scores HBP pondérés ne voyagent pas encore tous depuis le pipeline mining vers `append_block`.

### 1.4 EconomicRoot C (~95 %)

- v1 : `index\|ts\|prev\|graph\|merkle\|pol` — **inchangé**.
- v2 (si `hash_version>=2` + `economic_root`) : même préfixe + `\|v2\|<root>`.
- Blocs anciens sans root : toujours vérifiables.
- Fallback Python mix merkle **seulement** si `.so` pré-v2.

### 1.5 Oracle (~40 %)

Probe CoinGecko (ping, BTC, USDT, ticker `artcb`) + Frankfurter.  
**USDT/BTC ne sont PAS copiés comme prix ARTCB** (ce serait inventer).  
Ticker ARTCB absent → `live=False`, `artcb_usd=0`, DEBUG « NOT live ».  
`ARTCB_USD_PRICE` = override opérateur documenté.  
Frais : D-025 vault (pas mint, pas remaining 21M). Le remaining 21M ne baisse que par `R_block`.

### 1.6 Stripe GHA

Fichiers :
- `.github/workflows/stripe-priority.yml` (push sur cette branche)
- `.github/workflows/stripe-job-payment.yml` (`workflow_dispatch` / `workflow_call`)
- `.github/workflows/tests.yml` injecte le secret dans pytest (jamais écrit dans `.env`)

Secret : `secrets.KEY_API_STRIPE_ACTION` (jamais loggé, jamais commité).  
Tests : `tests/test_stripe_priority_job.py` — **skip** si env vide.

Ce runtime cloud : `KEY_API_STRIPE_ACTION` **unset** → skip local OK.

**GHA réel (push `4debc5d`)** : https://github.com/vgactech/artcb/actions/runs/33206660774  
- conclusion **success**
- « KEY_API_STRIPE_ACTION is set (value not printed) »
- bash `mode=unknown` (préfixe non matché tel quel ; probable CR/LF — trim ajouté ensuite). Python `.strip()` avant l’appel API.
- pytest Stripe : **6 passed** en 1,06 s (create+cancel + conservation, **pas** skip)
- Preuve protocole : `minted_satoshi == 0`, cap 21 M inchangé

Chemin TEST : PaymentIntent `capture_method=manual` puis **cancel**. Live key : même geste, montant plafonné, jamais de capture.

---

## 2. OVH — résultats live (pas de fiction)

Public : `http://152.228.144.34:8000`

| Appel | HTTP | Corps / note |
|-------|------|----------------|
| `GET /health` | **200** | `{"status":"healthy","version":"0.3.0","bootstrap_mode":false,"pqc":{"available":true,"algorithm":"ML-DSA-65"}}` |
| `GET /api/v1/health` | **200** | chain `valid:true`, `block_count:0` (fichier chaîne vide OK) |
| `GET /api/v1/chain/verify` | **200** | idem |
| `GET /api/v1/economics/params` | **404** | Not Found |
| `GET /api/v1/economics/emission` | **404** | Not Found |
| `GET /api/v1/economics/hbp` | **404** | Not Found |
| `GET /api/v1/economics/identity` | **404** | Not Found |
| `GET /api/v1/mining/protocol` | **404** | Not Found (re-probe 2026-08-28T20:10Z) |
| `POST /api/v1/economics/settle` | **405** | Method Not Allowed (pas la route 164) |

**Conclusion :** OVH est **up** et n’exécute **pas** cette branche. Ne pas affirmer que le serveur tourne le câblage 164. Re-probe identique après le commit code.

### Auth / ops

| Canal | Résultat |
|-------|----------|
| Doppler `DOPPLER_TOKEN` | **HTTP 401** `Invalid Auth token` — identique à la passe précédente. **Aucun token inventé.** |
| SSH `ubuntu@152.228.144.34` | `Permission denied (publickey)` — `~/.ssh` n’a que `known_hosts`, **aucune** clé privée |
| `OVH_CONSUMER_KEY` | présent dans l’env ; non utilisé (révoqué historiquement) |

---

## 3. H_adult mining

`ADULT_AGE_YEARS=18`. Compteur live = registry.  
`H_REF=1e6` **inchangé**. Pas de chiffre ONU WPP inventé.  
Ancres HBP 4,15e9 / 8,3e9 **provisoires**.  
Provider/Worker **50/50 = point de départ** (D-025).

---

## 4. Trous restants (%)

| Trou | % | Bloquant ? |
|------|---|------------|
| Mining sans MachineRegistry → PoL héritage | ~30 % du câblage mining | Oui pour « tout le monde en e2e » |
| HBP scores / provider scores pas toujours sur `append_block` mining brut | ~15 % | Moyen |
| Oracle ARTCB listé | 0 % ticker | Conversion USD→satoshi |
| WPP 18+ daté | 0 % | Q-E03 |
| OVH = cette branche | 0 % | Déploiement |
| Stripe réel ce runtime | skip | GHA peut le faire |
| P2P exige identity | 0 % | Réseau |
| Délai RETIRE/TRANSFER | non figé | Q-retire |
| Protocole « fini » | **non** | — |

---

## 5. DEBUG traces (extraits)

```
HBP(H) h_adult=5.0 rate=0.1000000006
fleet_owner_share N=5 P=0.470743750000
native C EconomicRoot v2 index=6 root=b1ae484eb2080cdd
C v2 hash index=6 eco=b1ae484eb208 -> 0c522f87c6fce5dc
WorkID W-resume-offline -> SETTLED
USD→ARTCB oracle NOT live (forced stub / unlisted)
```

---

## 6. Erreurs rencontrées + correctifs

| # | Symptôme | Cause | Correctif |
|---|----------|--------|-----------|
| 1 | Doublon `artcb_build_canonical_v2` à la compilation | Deux implémentations dans `libartcb_chain.c` | Fichier C réécrit, une seule v2 (vide = v1) |
| 2 | `_compute_dynamic_epoch` cassé | Patch `_resolve_adult_h` a avalé le corps | Fonctions séparées |
| 3 | `ImportError fetch_artcb_usd_quote` | Oracle réécrit en parallèle (USDT comme prix ARTCB) | Merge : probes riches, **pas** USDT=ARTCB ; alias `fetch_artcb_usd_quote` |
| 4 | `quote_fee_satoshi` raise si prix 0 | « never 0% » vs « ne pas inventer » | Stub `live=False`, `fee_satoshi=None` |
| 5 | Secret Stripe absent ici | Pas dans l’env cloud | Skip local + workflow GHA |
| 6 | OVH economics 404 | Déploiement ≠ cette branche | Documenté, pas de claim |

Simu 164 : **0 fail**. C `test_chain` : **all C tests passed**.

---

## 7. Fichiers clés

- `src/c/libartcb_chain.c` / `.h` — ABI v2
- `src/artcb/chain/ffi.py`, `chain/manager.py`
- `src/artcb/mining/protocol.py`, `mining/identity.py`, `mining/pipeline.py`
- `src/artcb/economics/oracle.py`, `job_payment.py`, `identity.py`, `workid.py`
- `src/artcb/payments/stripe_jobs.py`
- `src/api/economics_routes.py`, `mining_routes.py`, `deps.py`
- `.github/workflows/stripe-priority.yml`
- `tests/test_e2e_protocol_164.py`, `test_economic_root_native.py`, `test_stripe_priority_job.py`, `test_oracle_fees.py`

---

## 8. Pytest

Commande : `PYTHONPATH=src ARTCB_ORACLE_FORCE_STUB=1 python3 -m pytest tests/ -q --tb=short`  
Log : `logs/20260828_pytest_rapport164.txt`

**584 passed, 21 skipped, 0 failed** (163 était 554 / 20 skipped). Stripe local skip inclus dans les 21.

Stripe local : skip si `KEY_API_STRIPE_ACTION` unset — **attendu**.

Workflows : `.github/workflows/stripe-priority.yml` et `.github/workflows/stripe-job-payment.yml` (secret `KEY_API_STRIPE_ACTION`, jamais loggé).

---

## 9. Git / PR

Branche uniquement : `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**Pas de merge `origin/main`.**  
`gh pr list --head` : **aucune PR ouverte** (outil ManagePullRequest absent de cette session ; `gh` en lecture seule).  

Compare : https://github.com/vgactech/artcb/compare/main...cursor/tokenomics-21m-hbp-owner-decay-3fcb
