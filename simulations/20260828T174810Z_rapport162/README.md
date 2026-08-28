# Simulations rapport 162 — 20260828T174810Z

Python réel, `PYTHONPATH=src`, aucun mock économique. DEBUG on.
Stdout DEBUG = `run.log` (copie `logs/20260828_sim_rapport162_run.log`).

| Run | Fichier de sortie | Contenu |
|-----|-------------------|---------|
| `01_emission` | `out/01_emission.json` | R(H), 210k not cutting, time-normalization vs naive |
| `02_owner_decay` | `out/02_owner_decay.json` | M1 100%, fleet P(N), offline vs economic count |
| `03_hbp_finder` | `out/03_hbp_finder.json` | HBP envelope + Finder 25/j vs 272 |
| `04_workid_partition` | `out/04_workid_partition.json` | unique WorkID, hash partition, missing PB |
| `05_provider_worker` | `out/05_provider_worker.json` | 50/50 start, weighted, dynamic clamp |
| `06_settlement_economic_root` | `out/06_settlement_economic_root.json` | conservation + root sensitivity + live vs 162 |
| `07_fees_dividend_lock` | `out/07_fees_dividend_lock.json` | USD fee cap, vault, 30-day lock |
| `08_identity_machines` | `out/08_identity_machines.json` | Q=100, binding<=1, machine states |
| `09_monte_carlo` | `out/09_monte_carlo.json` | seed=42 runs=2000 12-month worlds |
| `09_monte_carlo_csv` | `out/09_monte_carlo_runs.csv` | per-run issued/H/interval |
| `10_code_gap_inventory` | `out/10_code_gap_inventory.json` | function-by-function 162 vs src/artcb/economics |

| `11_post_impl_live` | `out/11_post_impl_live.json` | Live modules after D-025 code: 210k, time-norm, M1, A2=A3 |

## Constantes dérivées (pas inventées)
- `OWNER_DECAY_K` = 0.025317807984 depuis exemples utilisateur P(3)=49%
- `TARGET_BLOCK_SECONDS` = 600.0 (TOKENOMICS §4.1 déjà documenté)
- `FEE_CAP_USD` = 0.000311 (OpenChainBench Base p50 2026-08-26)
- Finder sim = 25/j (utilisateur 20–30)

## Échecs
_aucun_

