# R331 — exécuter les ouverts (#77, #86, R330, P2P tip)

**2026-09-12T20:55:00Z** — `CERTIFIED_100=false`.

## Faits mesurés (avant / pendant)

- Live seeds `git_sha` = `c4ca2ed…` = `origin/main` (avant ce push).
- Public tip **1147×4** `4e2a9481…`, `ledger_mode=split_v1`.
- Pollution : mémo private → tip public stable ; mémo public → 1147 (PASS).
- Auto VC : view **20→21**, primary **ovh-node-2**, Q=4 NEW-VIEW (`auto_vc_measured=true`). Cause racine : `primary_of(19)=mac-node-local` sans tunnel → `next_reachable_view`.
- #77 live277 sur `c4ca2ed` : phase1 SHA+binding **PASS** ; A3/A7 **FAIL NOT_PROVEN** car forge SSH `:22` **timeout** depuis ce LAN (posts `{}`). NEW-VIEW rows VC aussi SSH-dépendantes → FAIL.

## Correctifs livrés (ce tour)

1. `POST /api/v1/consensus/pbft/audit-sign` — forge PREPARE/VC265 avec clé locale + claimed NodeID, **sans** muter l’état PBFT.
2. `run_live277_issue77.py` : forge HTTPS d’abord, SSH en secours ; HTTP seeds = `*.artcb.me`.
3. P2P `public_sync_cursor` (déjà) + tests R330/R331.
4. Mac restart : wait loop health + `chain/status` public tip.
5. Probe ORG body multi-nœud (ACL session honnête si 401).

## Suite immédiate après push

1. follow-main ×4 (timers) + Mac pull/restart.
2. Relancer `scripts/run_live277_issue77.py` (skip N04 si SSH netem impossible).
3. Relancer `scripts/artcb_r331_execute_open_p0.py` + height audit P2P.
4. Mettre à jour cette matrice avec SHA déployé + verdicts A3/A7.
