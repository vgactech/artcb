# Simulation e2e165 — E2E Protocol Integration

UTC: 20260828T220828Z
DEBUG: on. No economic mocks.
Security modules: ENABLED (Anti-Sybil + Slashing). Sequential sim uses ARTCB_MIN_BLOCK_INTERVAL_SEC=0.
hmax_frozen: false (adult max unfrozen; no UN WPP lock).

## Scenario
Users A,B,C,D,E. Machines A:M1 (100%), A:M2→B, A:M3→C, A:M4→D, A:M5→E (P(N) changes).
Jobs: petit, gros, simultanés, plus de PB, annulé, partiel (PB manquant + requeue), JobPayment no-mint,
providers_nonzero (JP1+JP2 scores), stripe_down_no_block (Stripe fail ≠ chain fail).
Load: faible / moyenne / forte.
Attacks: double binding B, double WorkID, owner cut B, offline GRACE→OFFLINE, transfer M2, fake human, tamper EconomicRoot.
Wallets: Σ balances = supply (chain contributors). Oracle: live probes; unlisted → conversion refused (not 0%).

## Outputs
See `out/*.json` and `run.log`.

Failures: none
