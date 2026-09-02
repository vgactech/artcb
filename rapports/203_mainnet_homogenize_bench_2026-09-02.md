# Rapport 203 — Homogénéisation mainnet + benches officiels (conditions réelles)

**Horodatage :** 2026-09-02T18:20:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`, `OPERATOR_MAINNET_CERTIFICATION_GO=false`)  
**Décision :** D-053  

Ce rapport ne publie **pas** de TPS mainnet. Le 90 TPS de `logs/bench_artcb_20260803T115235Z.json` reste un **bench local historique**.

## 1. Audit GitHub (mesuré, pas le résumé)

| Affirmation | Vérifié |
|-------------|---------|
| `origin/main` au départ de la tâche | `642b0e10f5b375e2b990b1fe23d5084146899e95` — **aucun commit après** jusqu’à cette PR |
| PR #49 | **MERGED** 2026-09-02T16:48:18Z |
| PR #50 | **OPEN** (inventaire 202) puis étendue ici |
| `certification_gate()` | AND DV-01…07 PASS + live BFT + V locked + **GO opérateur** ; GO = `False` |
| Tests `test_*.py` | **80** fichiers, **26** e2e (avant 203) ; + `test_e2e203_official_bench.py` |
| Scripts bench | `scripts/bench_artcb_real.py`, `scripts/benchmark_performance.py` |
| « Le bench officiel peut partir » | **Cas A** (outils) **oui**. **Cas B** (campagne reproductible 4 nœuds même SHA) **non tant que n2/n4 ne sont pas keep-book** |

## 2. Accès réel des nœuds (cette session)

| Nœud | SSH | Comment |
|------|-----|---------|
| OVH1 `152.228.144.34` | **oui** | `OVH_SSH_PRIVATE_KEY` / Doppler `artcb-blockchain` `SSH_PRIVATE_KEY` |
| OVH2 `151.80.107.29` | **non** (publickey) | Doppler `artcb-2` **sans** `SSH_PRIVATE_KEY`. API cloud **OK**. Rescue : authorized_keys = seulement `artcb-ovh-node-2`. Snapshot Glance `artcb-ovh2-keepbook-203` (`59f50bdf-…`). |
| AWS3 `51.44.222.232` | **oui** | Doppler `artcb3` `AWS_ACCESS_KEY_ID` (Cursor `AWS_API_KEY_AGENT_3` ≠ Doppler, STS fail). Instance Connect + clé persistée. SG **80/443 ouverts**. |
| OVH4 `91.134.45.8` | **non** | `KEY_API_ARTCB_DOPPLER_4` absent. Clés OVH Cursor 403 « credential does not exist » (pas le nic xy4589). |

## 3. Métrologie (code D-053)

`/api/v1/metrics` publie désormais :

- `measured_bandwidth_mbps` — octets observés pendant le sleep
- `estimated_bandwidth_mbps` — valeur optimizer (peut être convention 100)
- `fallback_bandwidth_mbps`
- `bandwidth_source` = `measured` \| `idle_fallback` \| `fast_boot` \| `psutil_missing` \| `error`
- `metrics_timing.network_sample_sleep_seconds` (0.5) — le RTT HTTP ~760 ms **n’est pas** la latence de traitement

## 4. Protocole officiel (4 campagnes séparées)

1. **Machine** — `scripts.bench_artcb_real` sur chaque VM (PQC, append isolé), CPU/RAM, min/med/max, n, SHA.
2. **WAN** — ping/iperf3 matrice 4×4 ; **jamais** `bandwidth_mbps` idle.
3. **Chaîne locale** — sign/verify/append/verify chain sur **tempdir**, pas le livre live.
4. **Distribuée** — TX → nœud → propagation → confirmation ; TPS soutenu / max, P50/P95/P99, erreurs. **Interdit** tant que les 4 SHA ne sont pas identiques.

Script : `scripts/run_sim203_mainnet_homogenize_bench.py`.

## 5. Live après keep-book (à compléter par la sim 203)

Voir `simulations/*_e2e203_mainnet_homogenize_bench/17_summary.json`.

## Interdits

- Pas d’invention de solde / bloc / SHA.
- Pas de wipe `blocks.jsonl`.
- Pas de `certified_distributed_mainnet=true`.
- Token / mots de passe / PEM non affichés.
