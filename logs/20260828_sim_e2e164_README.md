# Simulation 164 — End-to-End Protocol Integration

UTC folder: `20260828T194555Z_e2e164`

Live modules from `src/artcb/economics/` + `src/artcb/mining/protocol.py` + native C hash v2.
No economic mocks. DEBUG on (`run.log`).

Does **not** re-run simulations 162/163.

## Pipeline (single execution)

HumanID → MachineID → WalletID → HumanBinding → JobID/WorkID → Capacity → Partition → PB → PoL → Provider/Worker → HBP → OwnerDecay → EconomicRoot → BlockHash → Settlement → wallet balances

## Outputs

| File | Content |
|------|---------|
| `out/00_summary.json` | H_adult, supply ≤ 21M, attacks, wallets |
| `out/00_manifest.json` | failures list |
| `out/01_bootstrap.json` | A,B,C,D + M1–M4 |
| `out/02_jobs.json` | small / large / simultaneous / cancelled / partial |
| `out/03_blocks_jobs_network.json` | low/medium/high load + missing PB |
| `out/04_m5_pn_change.json` | A adds M5→E, P(N) changes |
| `out/05_offline_resume.json` | GRACE/OFFLINE then resume |
| `out/06_attacks.json` | 7 attacks must REJECT |

## Run

```
PYTHONPATH=src python3 simulations/20260828T194555Z_e2e164/run_all.py
```
