# Rapport 164 — Simulation E2E protocole + EconomicRoot C + Stripe + OVH

**Horodatage UTC :** 2026-08-28T20:08:00Z  
**Branche :** `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**HEAD :** `509e537`  
**Dump / audit ChatGPT de HEAD `f6c9c59` :** lu ; **simulations 162/163 non relancées.**  
**Simulation canonique :** `simulations/20260828T200518Z_e2e164/` (`failures: []`)  
**Pytest :** `logs/20260828_pytest_rapport164_full.txt` — **584 passed, 21 skipped, 0 fail**  
**Langue :** rapport FR, code EN. DEBUG ON. **Aucun mock des chiffres économiques.**  
**Ne jamais écraser** 160, 161, 162, 163.

**554 verts (163) et 584 verts (164) ≠ protocole complet.**

---

## Avancement honnête

| Volet | 163 | 164 | Note |
|-------|-----|-----|------|
| Modules economics isolés | ~88 % | ~92 % | JobPayment, oracle, ProtocolEngine |
| **Intégration e2e mining/API** | **~35 %** | **~78 %** | Une exécution `ProtocolEngine` ; mining brut **sans** machines → PoL héritage |
| Oracle USD→ARTCB | 0 % live | **~55 %** | Probes HTTPS **réels** (CoinGecko + Frankfurter). Ticker ARTCB **absent** → conversion **refusée** (`fee_satoshi=None`), pas 0 % inventé |
| Hash C `EconomicRoot` | workaround Python | **oui (v2 natif)** | v1 inchangé ; v2 exige `economic_root` |
| Stripe JobPayment | 0 % | **workflow GHA OK + run success** | Ce runtime cloud : secret **absent** → live KO. GHA `33206660774` / `33206967696` = success (secret injecté, jamais loggé) |
| OVH = cette branche | non | **non** | Health 200 ; routes economics/mining 164 → **404** |
| **Global vs 162 (exécution unique)** | ~82 % modules | **~80 % câblé** | Plus strict que « modules écrits ». Pas fini. |

---

## 1. Décisions actées (pas de recul)

D-014 21 M. D-024 géopopulation, **pas** de halving 210k. D-025 : M1=100 % toujours ; extras même P(N_econ) P(2)=50 % P(3)=49 % floor 10 % ; time-norm R(H)×dt/600 ; vault ≠ remaining ; binding ≤1 externe ; lock 30 j ; P/W 50/50 si providers ; HBP 10→60→20 dans l’enveloppe ; créateur bootstrap 100 % puis H0=100 ; Finder par défaut ; frais → vault.

**Pas de nouveau D-xxx.** EconomicRoot natif C = implémentation de D-025 (plus le mix merkle Python, sauf fallback `.so` pré-v2).

---

## 2. Simulation 164 — preuves

Dossier : `simulations/20260828T200518Z_e2e164/`  
Script : `scripts/run_sim164_e2e.py` (vrai `ProtocolEngine`, pas un jumeau fictif).  
DEBUG : `run.log` (copie `logs/20260828_sim164_200518Z_run.log`).

Acteurs A,B,C,D,E. Machines A:M1 (100 %), A:M2→B, A:M3→C, A:M4→D, A:M5→E.

| Preuve | Valeur |
|--------|--------|
| `failures` | `[]` |
| Conservation Σ paiements = budget | **true** (tous les jobs) |
| Σ soldes wallets = supply | **49 000 000 000 satoshi = 490 ARTCB** |
| Supply ≤ 21 M | **true** |
| P extras N=5 | **47,074375 %** (`02_m5_p_n.json`) |
| H_adult live | **5** = `HumanRegistry.verified_adult_count` (18+) |
| `hmax_frozen` | **false** (pas 8,3e9 gelé) |
| Hash | **v2 natif C** ; `chain_valid: true` |
| JobPayment | `mints: false`, distinct de `R_block` |
| PB manquant `pb3` | settle **40 ARTCB** (4/5) + requeue `W-partial:requeue:pb3` |

### Jobs

| Job | Bloc | Conservé | Note |
|-----|------|----------|------|
| petit | 0 | oui | M1, 50 ARTCB → A |
| gros | 1 | oui | M1–M4, split A/B/C/D |
| simultanés | 2+3 | oui | W-par-1 / W-par-2 |
| plus de PB | 4 | oui | 8 partitions |
| partiel PB manquant | 5 | oui | 40 ARTCB + requeue |
| JobPayment no-mint | 6 | oui | Stripe ≠ mint |
| annulé | — | — | `cancelled`, minted=false |

### Charge réseau

| Charge | N_max | n_partitions |
|--------|-------|--------------|
| faible | 12 | 5 |
| moyenne | 1 | 1 |
| forte | 1 | 1 |

### Attaques

| # | Attaque | Résultat |
|---|---------|----------|
| 1 | Double binding B | **REJECT_DOUBLE_BINDING** |
| 2 | Double WorkID `W-small` | **REJECT_DOUBLE_SETTLEMENT** |
| 3 | A coupe le paiement de B | **REJECT_OWNER_CUT_PAYMENT** / IMPOSSIBLE |
| 4 | M2 ACTIVE→GRACE→OFFLINE | N_A **5→5** |
| 5 | Transfert M2 → E | N_A **5→4**, N_E=1 (M1 de E), P_A extras **48,025 %** |
| 6 | Faux humain (adresse B réutilisée) | **FAKE_HUMAN** |
| 7 | Tamper EconomicRoot | root change (`3491a726…` → `61519c9e…`) |

Soldes (satoshi) : A 41,61 ARTCB ; B 45,05 ; C 21,61 ; D 7,20 ; E 0 (pas de travail après transfert). Σ = 490.

Runs antérieurs conservés (non écrasés) : `20260828T194555Z_e2e164`, `195611Z`, `195646Z`, `200447Z`. Canonique = **200518Z** (après fix HumanID ≠ wallet).

---

## 3. Câblage mining / API (~78 %)

Une exécution :

```
H_adult → R(H)×dt/T → HBP → Worker → Provider → OwnerDecay
→ Settlement → EconomicRoot C v2 → BlockHash → soldes contributeurs
```

- `ProtocolEngine` (`src/artcb/mining/protocol.py`)
- `MiningPipeline.bind_identity` + `ChainManager.bind_identity`
- Contributors : `machine_index`, `owner_address`, `human_id`, `work_id`, `bound_human_address`, `n_economic`, `work_weight`
- API : `/api/v1/mining/protocol`, `/protocol/status`, `/economics/h-adult`, `/oracle`, `/jobs/priority`, `/webhooks/stripe`, humans/workids
- H mining = registry 18+, alias `verified_humans` conservé

**Encore ouvert :** un nœud qui mine **sans** machines enregistrées reste en split PoL héritage. Scores HBP pondérés pas toujours poussés depuis le pipeline texte brut.

---

## 4. EconomicRoot C — **oui**

- v1 : `index|ts|prev|graph|merkle|pol` — **byte-identique** si root vide.
- v2 : `…|v2|<economic_root>` si `hash_version>=2` **et** root présent.
- Blocs historiques sans root : toujours valides.
- Champ top-level `economic_root` **avant** `economics` (C `strstr`).
- Fallback Python mix merkle **seulement** si `.so` pré-v2.
- Tests C : `make -C src/c clean all test` → `all C tests passed`.
- Fix 164 : **ne plus** copier `human_id` dans `bound_human_address` (HBP partait vers `H-A` au lieu du wallet).

---

## 5. Oracle (~55 %)

Sources live (timeout 8 s, User-Agent `ARTCB-oracle/164`) :

- CoinGecko ping, BTC/USD, USDT/USD, ticker `artcb`
- Frankfurter USD→EUR

**Preuve sim 200518Z :** `probe_ok=true`, BTC=77530, USDT=0,999891, EUR=0,85889, **artcb_listed=false**.  
USDT/BTC = **liveness only**, jamais copiés comme prix ARTCB.  
Unlisted → `live=False`, `fee_satoshi=None` (pas 0 % de frais).  
Override documenté : `ARTCB_USD_PRICE` ou argument `artcb_usd_price=` (sim : 1,0 USD → 100 satoshi, `mints=false`, vault).  
Frais D-025 → UniversalDividendVault, **pas** mint, **pas** remaining 21 M.

---

## 6. Stripe — workflow OK / live ce runtime **KO** / GHA **OK**

| Élément | État |
|---------|------|
| Secret GitHub Actions | `secrets.KEY_API_STRIPE_ACTION` dans `tests.yml`, `stripe-job-payment.yml`, `stripe-priority.yml` |
| Ce runtime cloud | **unset** (`KEY_API_STRIPE_*` / `STRIPE_*` absents) |
| Live PaymentIntent **ici** | **KO** — raison : secret non injecté dans le pod Cloud Agent |
| GHA live | **OK** — runs `33206660774` et `33206967696` **success** (secret injecté, 6 tests, valeur jamais loggée). Prefix check trim CR/LF (`mode=test` vs `unknown`) |
| Script CI | `scripts/stripe_job_payment_ci.py` ici → `stripe_skipped: true`, `mints: false` |
| Anti-spam | floor 50 cents |
| Webhook | idempotence `event_id` ; `artcb_mints=true` **rejeté** |
| Capture | `manual` + **cancel** ; `sk_live` refusé sur le workflow JobPayment dédié |
| Mint | **interdit** (`REJECT_STRIPE_MINT`) |

JobPayment ≠ R_block. La clé n’est jamais loggée ni commitée.

---

## 7. OVH — ce qui a été réellement hit

Public : `http://152.228.144.34:8000`

| Appel | HTTP | Note |
|-------|------|------|
| `GET /health` | **200** | healthy, v0.3.0, bootstrap_mode=false, ML-DSA-65 |
| `GET /api/v1/health` | **200** | chain valid, **0 blocs**, fichier chaîne vide OK |
| `GET /api/v1/chain/verify` | **200** | idem |
| `GET /api/v1/economics/params` | **404** | ancienne image |
| `GET /api/v1/economics/h-adult` | **404** | cette branche **absente** |
| `GET /api/v1/economics/oracle` | **404** | |
| `GET /api/v1/mining/protocol/status` | **404** | |

**SSH** `ubuntu@152.228.144.34` : `Permission denied (publickey)`.  
**Doppler** `DOPPLER_TOKEN` : HTTP 401 `Invalid Auth token`. **Aucun credential inventé.**  
Script prêt : `scripts/deploy_ovh.sh` (défaut IP 152.228.144.34, branche en argument). Déploiement **impossible** sans SSH.

---

## 8. Erreurs en cours de route + correctifs

| # | Symptôme | Cause | Correctif |
|---|----------|--------|-----------|
| 1 | Doublon `artcb_build_canonical_v2` à la compile | deux implémentations C | une seule v2 (vide = v1) |
| 2 | `quote_fee_satoshi` raise si prix 0 | « pas 0 % » vs « ne pas inventer » | `live=False`, `fee_satoshi=None` |
| 3 | Sim 164 `failures: oracle price 0` | unlisted compté comme fail | refuse conversion = **succès honnête** |
| 4 | EconomicRoot ProtocolEngine ≠ chain | `human_id` copié comme bound wallet | bound = wallet only (`5ed39c4`) |
| 5 | Stripe live ici | secret GHA non injecté | skip + workflow correct |
| 6 | OVH economics 404 | box ≠ cette branche | documenté, pas de claim |
| 7 | Doppler 401 / SSH refus | token/clé invalides (cas connu) | pas d’invention de secrets |
| 8 | Double settle lignes 2 vs 3 | même bug HumanID | roots identiques après fix (`902627f46fa55647`) |

---

## 9. Tests

Commande : `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line`  
Log : `logs/20260828_pytest_rapport164_full.txt`  
**584 passed, 21 skipped, 0 fail** (180,62 s).  
C : `make -C src/c clean all test` → all C tests passed.  
Nouveaux : `tests/test_e2e_protocol_164.py`, `test_economic_root_native.py`, `test_oracle_fees.py`, `test_stripe_priority_job.py`.

Stripe live pytest **skip** si secret absent — **attendu**.

---

## 10. Trous restants

| Trou | Bloquant ? |
|------|------------|
| Mining sans MachineRegistry → PoL héritage | Oui pour « tout le monde en e2e » |
| WPP 18+ daté (Q-E03) | Ancres HBP encore provisoires |
| Ticker ARTCB listé | Conversion live USD→satoshi |
| OVH = cette branche | Déploiement SSH |
| Stripe réel **ce** runtime | GHA peut le faire |
| P2P exige identity | Réseau |
| Délai RETIRE/TRANSFER | Q-retire |

---

## 11. Git / PR

Branche uniquement : `cursor/tokenomics-21m-hbp-owner-decay-3fcb`  
**Pas de merge `origin/main`.**  
Compare : https://github.com/vgactech/artcb/compare/main...cursor/tokenomics-21m-hbp-owner-decay-3fcb

---

## 12. Fichiers clés

- `src/c/libartcb_chain.c` / `.h` — ABI v2
- `src/artcb/chain/ffi.py`, `chain/manager.py`
- `src/artcb/mining/protocol.py`, `mining/identity.py`, `mining/pipeline.py`
- `src/artcb/economics/oracle.py`, `job_payment.py`, `fees.py`
- `src/artcb/payments/stripe_jobs.py`
- `src/api/economics_routes.py`, `mining_routes.py`, `deps.py`
- `.github/workflows/stripe-job-payment.yml`, `stripe-priority.yml`, `tests.yml`
- `scripts/run_sim164_e2e.py`, `scripts/stripe_job_payment_ci.py`, `scripts/deploy_ovh.sh`
