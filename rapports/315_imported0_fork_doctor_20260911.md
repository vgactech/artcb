# R315 — imported=0 + Node Join / Network Recovery (first slice)

**UTC :** 2026-09-11T17:40:00Z  
**CERTIFIED_100 :** `false`  
**git_sha live (seeds) :** `906e8bf4…` (R314 still on main until this commit)

## Verdict P0 — why `received=783` / `imported=0`

**A — FORK_AT_BLOCK0 (real divergence), not a transport bug.**

| | Mac (`./data/chain/blocks.jsonl`) | Seed `artcb.me` |
|--|--|--|
| `network_id` label | `artcb-mainnet-1` | `artcb-mainnet-1` |
| `genesis_hash` label | `genesis-artcb-mainnet-1` | `genesis-artcb-mainnet-1` |
| **block 0 content hash** | `8ee26e84324036bd…` **private** | `b8a7d5ef50052790…` **public** |
| tip | index **8** `366a6d259ea0206b…` | tip ≠ Mac; **783** public blocks |
| visibility | **10/10 private** (`public_blocks_local=0`) | public book |

Same labels ≠ same chain. Indices 0…8 are **all unequal**.

Anonymous P2P (`decide_public_import`) correctly refuses seed public blocks:

- mostly `reject:wrong_index`
- when index matches next tip slot: `reject:wrong_prev_hash` (seed prev ≠ Mac tip)

Live re-measure: pull `peer_artcb_me_443` → **received 783 / imported 0** again.  
`783 == seed.public_blocks_local` ⇒ payload is the full public set; endpoint is **not** broken (class **C** false).  
Class **D** is half-true by design: `/p2p/sync` = public-only anonymous path ≠ official full-book replica.

Extra local anomaly: **duplicate index 8** (two hashes, same prev) on Mac disk.

Empty Mac *would* accept seed block 0 (`append:extends_tip`) — so catch-up is blocked by the divergent private sandbox, not by HTTPS.

## Recovery without wipe (seeds untouched)

1. Run `scripts/artcb_r315_fork_diagnose.py` → expect `FORK_AT_BLOCK0`.
2. Optional: `scripts/artcb_r315_quarantine_local_book.py --dry-run` then `--i-understand-local-only` (moves local book to `data/quarantine/…`, **does not delete**, **does not touch seeds**).
3. Restart Mac node on empty tip → HTTPS P2P / official replica catch-up.
4. Never force `prev_hash`, never new genesis, never wipe seed `blocks.jsonl`.

Quarantine **not executed** this tour (dry-run only) — needs explicit operator GO before moving the live Mac book.

## Tools added (Join / Recovery slice)

| Script | Role |
|--------|------|
| `scripts/artcb_r315_fork_diagnose.py` | common-ancestor / fork proof + `decide_public_import` sample |
| `scripts/artcb_doctor.py` | differential: OS/TPM/DNS/HTTPS/:8000/inbound/sync |
| `scripts/artcb_r315_quarantine_local_book.py` | local quarantine only |
| `src/artcb/p2p/sync.py` | pull response + flux now include `decision_tally` |

Doctor profile measured: **`HTTPS_RELAY`** (`:8000` timeout, `:443` OK, inbound FAIL).

## Architecture agreement (operator audit)

R315 target remains **Node Join + Network Recovery + Resumable Sync** (`artcb join` / network-manager / resumable sync). This commit is the **diagnosis + doctor + safe quarantine** foundation — not one-click join yet.

Identity separation (user ≠ machine ≠ node crypto ≠ SSH ≠ wallet ≠ TPM) and Wi‑Fi public as normal degraded mode are accepted design constraints.

## Still open

- Mac tip × seeds height (~8 vs ~1200+)
- Official replica catch-up after quarantine GO
- Inbound tunnel / PBFT fan-in Mac
- `swtpm` still installing via brew (~19h elapsed, not in Cellar)
- UI Thinking ≡ hook: `NOT_PROVEN_BY_ARCHITECTURE`
- Prompt ingest this turn: `ingest_skipped` HTTP 409 `not_extending` on seed write path

**CERTIFIED_100=false**
