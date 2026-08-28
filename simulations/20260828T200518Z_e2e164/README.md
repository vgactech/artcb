# Simulation 164 — E2E Protocol Integration

UTC: 20260828T200518Z
DEBUG: on. No economic mocks.

## Scenario
Users A,B,C,D,E. Machines A:M1 (100%), A:M2→B, A:M3→C, A:M4→D, A:M5→E (P(N) changes).
Jobs: petit, gros, simultanés, plus de PB, annulé, partiel (PB manquant + requeue), JobPayment no-mint.
Load: faible / moyenne / forte.
Attacks: double binding B, double WorkID, owner cut B, offline GRACE→OFFLINE, transfer M2, fake human, tamper EconomicRoot.
Wallets: Σ balances = supply (chain contributors). Oracle: live probes; unlisted → conversion refused (not 0%).

## Outputs
See `out/*.json` and `run.log`.

Failures: none
