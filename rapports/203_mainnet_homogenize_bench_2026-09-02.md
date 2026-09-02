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

## 5. Live mesuré après keep-book bundle `5b18eb88` (2026-09-02T18:21Z)

Livre public **identique × 4** : height **1**, `last_hash` `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce`, `chain_valid=true`. Certif **false**.

| | OVH1 | AWS3 | OVH2 | OVH4 |
|--|------|------|------|------|
| SHA | **`5b18eb88` main** | **`5b18eb88` main** | `f284180` feature | `f284180` feature |
| HTTPS domaine | https://artcb.me/health 200 | https://n3.artcb.me/health 200 | n2 :80 nginx 404 (pas keep-book) | n4 :80 nginx 404 |
| RAM Go | 7.57 | 1.86 | 7.57 | 7.57 |
| workers / chunk | 3 / 400 | 1 / 200 | 3 / 400 | 3 / 400 |
| `bandwidth_source` | **idle_fallback** | **idle_fallback** | champ absent (SHA ancien) | absent |
| measured_mbps | 0.0 | 0.0 | n/a | n/a |
| estimated_mbps | 100.0 (convention) | 100.0 | n/a | n/a |
| `/health` RTT | 204 ms | 184 ms | 186 ms | 178 ms |
| `/metrics` RTT | 772 ms (dont sleep 0.5 s) | 772 ms | 771 ms | 766 ms |

Premier `git fetch origin` sans credentials GitHub a **rétrolavé** OVH1/AWS3 vers `f8118ff` (origin/main stale local). Corrigé par **bundle** obligatoire si fetch échoue. `run_sim203` refuse désormais un SHA ≠ HEAD.

### Campagne 1 — machine (venv `.venv`, tempdir, **pas** le livre live)

Anti-Sybil burst du vieux script a crashé (intervalle 60 s). PQC + append sans sécu **OK** :

| Opération n=50 sauf mention | OVH1 avg ms | AWS3 avg ms | Labo 2026-08-03 avg ms |
|-----------------------------|-------------|-------------|-------------------------|
| ML-DSA-65 keygen | 45.96 | 26.85 | 0.140 |
| ML-DSA-65 sign 296 B | 47.86 | 32.43 | 0.279 |
| ML-DSA-65 verify | 44.64 | 28.62 | 0.121 |
| ML-KEM-768 gen | 40.29 | 29.45 | 0.062 |
| encapsulate | 40.23 | 25.01 | 0.067 |
| decapsulate | 38.61 | 29.91 | 0.063 |
| append_block() sécu OFF n=30 | 44.16 | 33.12 | 2.587 |
| verify() chaîne n=20 | 5.85 | 3.85 | 4.475 |

Le labo 0.14 ms n’est **pas** comparable (autre machine / autre binaire). Ces chiffres live sont la baseline machine officielle **partielle** (OVH1+AWS3).

### Campagne 2 — WAN ping (ICMP AWS ouvert cette session)

| src → dst | RTT avg |
|-----------|---------|
| OVH1 → OVH2 | 0.52 ms |
| OVH1 → OVH4 | 0.61 ms |
| OVH1 → AWS3 | 5.19 ms |
| AWS3 → OVH1 | 5.21 ms |
| AWS3 → OVH2 | 5.62 ms |
| AWS3 → OVH4 | 5.78 ms |

Pas d’iperf3 encore. `bandwidth_mbps=100` n’est **pas** un débit WAN.

### Campagnes 3–4

Chaîne locale isolée : append sans sécu ci-dessus. **Distribué sous charge : non mesuré** (SHA n2/n4 hétérogènes).

## 6. Ce qu’il reste pour un bench 4 nœuds

1. Mettre `SSH_PRIVATE_KEY` (PEM) dans Doppler **artcb-2** et **artcb-4** (ou `KEY_API_ARTCB_DOPPLER_4` + clés OVH4). Snapshot Glance OVH2 `artcb-ovh2-keepbook-203` déjà créé.
2. Keep-book bundle `5b18eb88` (ou plus récent `main`) sur n2/n4.
3. Relancer `scripts/run_sim203_mainnet_homogenize_bench.py`.
4. iperf3 mesh. Puis seulement campagne 4 (TPS distribué P50/P95/P99).


## Interdits

- Pas d’invention de solde / bloc / SHA.
- Pas de wipe `blocks.jsonl`.
- Pas de `certified_distributed_mainnet=true`.
- Token / mots de passe / PEM non affichés.
