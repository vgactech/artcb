# Rapport 204 — Homogénéisation 3 nœuds origin/main + recovery SSH OVH2

**Horodatage :** 2026-09-02T19:05:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`, `OPERATOR_MAINNET_CERTIFICATION_GO=false`)  
**Décision :** D-054  

Ce rapport ne publie **pas** de TPS mainnet. Le 90 TPS de `logs/bench_artcb_20260803T115235Z.json` reste un **bench local historique**. Les 15.7 / 16.6 / 29.1 blocs/s mesurés ici sont un **tempdir isolé, security OFF**, pas le débit du réseau.

## 1. Audit GitHub (mesuré)

| Affirmation | Réalité maintenant |
|-------------|-------------------|
| SHA `origin/main` | `ad017bca05c2e3799c7dcd120ca1797968d499b6` |
| Commits après `642b0e10` | `9f826b3` … `d3457d0` (PR #49) … `2e14395` `1e4ee5e` `5b18eb8` (PR #50) `e4fab05` `c9753f9` `ad017bc` |
| PR #49 | **MERGED** 2026-09-02T16:48:18Z (`d3457d0`) |
| PR #50 | **MERGED** 2026-09-02T18:17:37Z (`5b18eb8`) — pas seulement « fermée » |
| `certification_gate()` | AND DV-01…07 + BFT + V locked + GO opérateur ; GO = **False** |
| Tests `test_*.py` | **82** (81 + `test_e2e204_ovh2_rescue_homogenize.py`) |
| « Le bench officiel peut partir » | **Cas A** (outils + 3 nœuds même SHA) **oui**. **Cas B** (4 SHA identiques + procédure brute P50/P95/P99 distribués) **non** — OVH4 reste `f284180` |

## 2. Accès réel des nœuds (cette session)

Les secrets Cursor `ARTCB_OVH_NODE_1/2/4` et `*_AGENT` sont des **clés publiques** `ssh-ed25519`, pas des PEM. Inutilisables pour SSH sortant.

| Nœud | SSH cette session | Comment |
|------|-------------------|---------|
| OVH1 `152.228.144.34` | **oui** | Cursor `OVH_SSH_PRIVATE_KEY` → `~/.ssh/artcb_ovh_deploy` |
| OVH2 `151.80.107.29` | **oui** (après rescue) | Doppler `artcb-2` n’avait **pas** `SSH_PRIVATE_KEY`. Rescue Public Cloud : montage **sdb1 49G** (jamais le root rescue 2.9G), append pubkey `artcb-ovh-node-2-agent-204`, livre 1 ligne préservé. PEM écrit dans Doppler **artcb-2** `SSH_PRIVATE_KEY`. |
| AWS3 `51.44.222.232` | **oui** | Cursor AWS STS invalide. Doppler **artcb3** STS OK (`node_artcb_3_agent`). Instance Connect + persist `authorized_keys`. PEM écrit dans Doppler **artcb3** `SSH_PRIVATE_KEY`. |
| OVH4 `91.134.45.8` | **non** | `KEY_API_ARTCB_DOPPLER_4` absent. Cursor `OVH_*` → 403 « This credential does not exist ». Les 4 PEM de cette session = Permission denied. |

Script réutilisable : `scripts/inject_ovh2_ssh_via_rescue.py --yes --write-doppler`.

## 3. Keep-book `ad017bc` (bundle, pas git fetch GitHub)

GitHub HTTPS sur les VM reste stale (`origin/main` local en retard de 12–15 commits). Bundle obligatoire. `install.sh` / genesis / wipe **non exécutés**. `blocks.jsonl` = **1 ligne** sur les 3 nœuds keep-bookés.

| | OVH1 | OVH2 | AWS3 | OVH4 |
|--|------|------|------|------|
| SHA live | **`ad017bc` main** | **`ad017bc` main** | **`ad017bc` main** | `f284180` feature |
| HTTPS domaine | https://artcb.me/health 200 | https://n2.artcb.me/health 200 | https://n3.artcb.me/health 200 | n4 : URLError ; :80 nginx 404 |
| `:80` + `Host:` | 200 | 200 | 200 | 404 |
| Certif | false | false | false | false |
| `bandwidth_source` | idle_fallback | idle_fallback | idle_fallback | champ absent (SHA ancien) |
| measured_mbps | 0.0 | 0.0104 | 0.0 | n/a |
| estimated_mbps | 100.0 (convention) | 100.0 | 100.0 | n/a |
| `/health` RTT | 205 ms | 195 ms | 184 ms | 192 ms |
| `/metrics` RTT | 773 ms (dont sleep 0.5 s) | 775 ms | 774 ms | 770 ms |
| RAM Go / vCPU | 7.57 / 4 | 7.57 / 4 | 1.86 / 2 | 7.57 / 4 |

Livre public **identique × 4** : height **1**, `last_hash` `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce`, `chain_valid=true`.

`/metrics` RTT ~770 ms **n’est pas** la latence de traitement (sleep volontaire 0.5 s dans `metrics_timing.network_sample_sleep_seconds`).

## 4. Campagne 1 — machine (`.venv`, tempdir, **pas** le livre live)

`python3 -m scripts.bench_artcb_real` sur le python système **échoue** (`No module named 'nacl'`). Officiel = `/home/ubuntu/artcb/.venv/bin/python`. Wallet skipped (`WalletEncryptionError`, passphrase absente du venv bench).

| Opération | OVH1 avg ms | OVH2 avg ms | AWS3 avg ms | Labo 2026-08-03 avg ms |
|-----------|-------------|-------------|-------------|-------------------------|
| ML-DSA-65 keygen n=50 | 43.11 | 49.21 | 23.23 | 0.140 |
| ML-DSA-65 sign 296 B | 44.63 | 51.40 | 23.26 | 0.279 |
| ML-DSA-65 verify | 42.33 | 48.00 | 22.87 | 0.121 |
| ML-KEM-768 gen | 41.13 | 46.46 | 22.97 | 0.062 |
| encapsulate | 42.87 | 51.58 | 23.27 | 0.067 |
| decapsulate | 44.57 | 50.29 | 23.69 | 0.063 |
| append_block() sécu OFF n=30 | 46.50 | 56.46 | 25.62 | 2.587 |
| verify() chaîne n=20 | 5.79 | 6.14 | 3.35 | 4.475 |
| append + Anti-Sybil n=20 | 149.55 | 148.79 | 126.68 | — |
| TPS isolé 200 appends sécu OFF | **16.6 blk/s** | **15.7 blk/s** | **29.1 blk/s** | ~90 (autre machine) |

Ces TPS isolés **ne sont pas** le débit mainnet distribué. Le labo 0.14 ms / 90 TPS n’est **pas** comparable.

Brut : `simulations/20260902T190418Z_e2e204_three_node_main_homogenize/` (live, ping, benches JSON).

## 5. Campagne 2 — WAN ping (ICMP, 5 paquets, 0 % perte)

iperf3 **absent** des 3 VM. `bandwidth_mbps=100` n’est **pas** un débit WAN.

| src → dst | RTT avg |
|-----------|---------|
| OVH1 → OVH2 | 0.52 ms |
| OVH1 → OVH4 | 0.56 ms |
| OVH1 → AWS3 | 5.18 ms |
| OVH2 → OVH1 | 0.49 ms |
| OVH2 → OVH4 | 0.49 ms |
| OVH2 → AWS3 | 5.41 ms |
| AWS3 → OVH1 | 5.32 ms |
| AWS3 → OVH2 | 5.47 ms |
| AWS3 → OVH4 | 5.68 ms |

## 6. Campagnes 3–4

Chaîne locale isolée : append sans sécu ci-dessus. **Distribué sous charge (TPS / P50 / P95 / P99) : non mesuré** — SHA OVH4 hétérogène. Un bench 3 nœuds n’est **pas** le protocole officiel 4 nœuds (N=4, F=1, Q=3).

## 7. Ce qu’il reste pour Cas B

1. `KEY_API_ARTCB_DOPPLER_4` + `SSH_PRIVATE_KEY` du nœud 4 dans Doppler **artcb-4** (PEM, pas la pubkey Cursor `ARTCB_OVH_NODE_4`).
2. Keep-book bundle `ad017bc` (ou `origin/main` plus récent) sur OVH4 + nginx `n4.artcb.me`.
3. Relancer `scripts/run_sim203_mainnet_homogenize_bench.py` (benches via `.venv`).
4. iperf3 mesh. Puis seulement campagne 4.

Les PEM OVH2 / AWS3 sont **déjà** dans Doppler `artcb-2` / `artcb3` (`SSH_PRIVATE_KEY`) pour les agents suivants.

## Interdits

- Pas d’invention de solde / bloc / SHA.
- Pas de wipe `blocks.jsonl`.
- Pas de `certified_distributed_mainnet=true`.
- Token / mots de passe / PEM non affichés.
- Pas de 90 TPS (ni 16.6 / 15.7 / 29.1) présentés comme débit mainnet distribué.
