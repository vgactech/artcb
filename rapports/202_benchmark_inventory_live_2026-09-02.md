# Rapport 202 — Inventaire tests + métriques hardware live pour benchmark officiel

**Horodatage :** 2026-09-02T16:57:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Bootstrap live :** OVH1 `/health` 200, SHA `642b0e10f5b375e2b990b1fe23d5084146899e95`, branche `main`, PQC ML-DSA-65, token non affiché  

Ce document **n’invente pas** de TPS live ni de débit WAN. Tout chiffre live ci-dessous a été lu sur `/health`, `/api/v1/metrics`, `/api/v1/system/hardware`, `/api/v1/system/optimization`, `/api/v1/chain/status` (HTTP :8000) et, pour OVH1 seulement, via SSH `lscpu`/`free`/`df`.

## 1. Ce qu’on a déjà (pour démarrer un bench officiel)

Trois couches distinctes :

| Couche | Où | Nature | Peut servir de bench officiel ? |
|--------|-----|--------|----------------------------------|
| **Tests pytest** | `tests/` (80 fichiers) | Correctness, pas de perf | Baseline fonctionnelle, pas un score TPS |
| **Bench scripts** | `scripts/bench_artcb_real.py`, `scripts/benchmark_performance.py` | Microbench local (IR, SHA-256 C, PQC, append_block) | Oui **si relancés sur les 4 VMs** avec horodatage + SHA |
| **Télémétrie live** | `GET /api/v1/metrics` + `/system/hardware` + `/health.machine` | CPU/RAM/disque/GPU/TPM/assurance A–E | Oui pour **fiche machine** ; **pas** un débit réseau réel (voir §5) |

## 2. Endpoints à capturer (protocole bench)

| Méthode | Chemin | Contenu |
|---------|--------|---------|
| GET | `/health` | SHA, branche, PQC, `certified_*`, bloc `machine` (TPM, virt, cloud, assurance) |
| GET | `/api/v1/metrics` | CPU%/RAM%/disque live + snapshot hardware + profil optimisation |
| GET | `/api/v1/system/hardware` | CPU cœurs, RAM Go, disque, GPU, réseau (snapshot boot) |
| GET | `/api/v1/system/optimization` | workers pool, chunk, max_contributors, flags IR/FAISS |
| GET | `/api/v1/chain/status` | height, last_hash, chain_valid |
| GET | `/api/v1/security/anti-sybil/metrics` | calibrage anti-Sybil (usage) |

CLI : `scripts/artcb_cli.py` commandes `metrics` / `system hardware` / `system optimization`.  
UI : `frontend/src/components/SystemMetrics.tsx` (vue V7).  
Tests dédiés : `tests/test_system_hardware.py`, `tests/test_hardware_identity_binding.py`, `tests/test_e2e192_hw_baremetal.py`, `tests/test_e2e196_hybrid_and_hw.py`.

## 3. Fiche machine live (2026-09-02T16:57Z, mesurée)

Livre public **identique × 4** : height **1**, `last_hash` `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce`, `chain_valid=true`. PQC **ML-DSA-65** `available=true`, AND `verify_hybrid_and`. **Aucun GPU** (`nvidia-smi` absent OVH1). Assurance hardware **E** (empreinte logicielle, pas de puce) × 4. `/dev/tpm0` **absent**. TEE/HSM **false**. Certif **false**.

| | OVH1 | OVH2 | AWS3 | OVH4 |
|--|------|------|------|------|
| IP | 152.228.144.34 | 151.80.107.29 | 51.44.222.232 | 91.134.45.8 |
| hostname | artcb-node-1 | node-artcb-ovh-2 | ip-172-31-8-93 | node-artcb-ovh-4 |
| git_sha | `642b0e10…899e95` | `f2841808…527de` | `f2841808…527de` | `f2841808…527de` |
| git_branch | `main` | `cursor/artcb-me-official-16d8` | idem | idem |
| kernel | 6.8.0-106-generic | 6.8.0-136-generic | 7.0.0-1011-aws | 6.8.0-136-generic |
| virt | kvm / OpenStack Nova | kvm | amazon / t3.small (sim 192) | kvm |
| cloud | ovh | ovh | aws | ovh |
| vCPU logical | 4 | 4 | 2 | 4 |
| vCPU physical (psutil) | 4 | 4 | 1 | 4 |
| freq API MHz | 2394.5 | 2394.5 | 2500.0 | 2400.0 |
| RAM total Go | 7.57 | 7.57 | 1.86 | 7.57 |
| RAM used live Go | 0.60 (7.9 %) | 0.58 (7.6 %) | 0.50 (27.0 %) | 0.57 (7.6 %) |
| disque total Go | 47.39 | 47.39 | 28.02 | 47.39 |
| disque used % | 9.1 | 7.6 | 13.5 | 7.6 |
| CPU live % | 2.4 | 0.0 | 0.0 | 0.0 |
| pool workers | 3 | 3 | 1 | 3 |
| chunk_chars | 400 | 400 | 200 | 400 |
| max_contributors | 10 | 10 | 10 | 10 |
| FAISS GPU | false | false | false | false |
| `/health` RTT | 200 ms | 188 ms | 190 ms | 183 ms |
| `/metrics` RTT | 764 ms | 772 ms | 776 ms | 764 ms |

OVH1 SSH (en plus de l’API) : Ubuntu **24.04.4 LTS**, CPU **Intel Core Processor (Haswell, no TSX)** KVM, 4 sockets × 1 cœur, swap **0**, load `0.08 0.06 0.02`, uptime **14 days**, `artcb.service` active, RSS ~**96 Mo** (`MemoryCurrent=96509952`), `NRestarts=0`, `blocks.jsonl` **1 ligne**.

AWS3 est le nœud **le plus petit** (t3.small, ~2 Go RAM, 2 vCPU) : le profil d’optimisation baisse workers à **1** et chunk à **200**. Les trois OVH d2-8 sont homogènes (~8 Go / 4 vCPU).

## 4. Tests pytest (registre)

- **80** fichiers `tests/test_*.py` (dont **26** `test_e2e*`).
- `LISTE_TESTS_ARTCB.md` : T-B01 indiquait 478 passed le **2026-08-05** (chiffre **périmé** ; la suite a grandi : e2e 168–201). Relancer `pytest tests/ -q` pour un compte officiel daté.
- Hardware : `test_system_hardware.py` (psutil, `/metrics`, `/system/hardware`, `/system/optimization`, classes réseau).
- Identité machine : `test_hardware_identity_binding.py`, e2e 191/192/196 (TPM honnête, pas d’invention NitroTPM).
- Perf/stress **fonctionnel** (pas un bench publié) : `test_pool_stress.py`, `test_pool_e2e.py`.
- Crypto : `test_pqc_crypto.py`, `test_e2e173_crypto_ovh2.py`, `test_e2e198_hybrid_and_call_sites.py`.
- Chaîne : `test_chain.py`, `test_e2e189_mainnet_genesis.py`.
- Captures pytest historiques : `logs/metrics_post_pqc.json` (157 passed / 24.75 s, 2026-07-08) ; `logs/metrics_post_aes.json` (141 passed / 21.34 s).

## 5. Benches déjà enregistrés (machine **locale** 2026-08-03, **pas** les 4 VMs)

Fichier : `logs/bench_artcb_20260803T115235Z.json` — script `scripts/bench_artcb_real.py` (50 rounds sauf mention). Rapport 106.

| Opération | avg ms | n |
|-----------|--------|---|
| ML-DSA-65 generate_keypair | 0.140 | 50 |
| ML-DSA-65 sign 296 B | 0.279 | 50 |
| ML-DSA-65 verify 296 B | 0.121 | 50 |
| ML-KEM-768 generate | 0.062 | 50 |
| KEM encapsulate | 0.067 | 50 |
| KEM decapsulate | 0.063 | 50 |
| append_block() sans sécurité | 2.587 | 30 |
| verify() chaîne | 4.475 | 20 |
| append_block + Anti-Sybil (2 contrib.) | 2.340 | 20 |
| WalletManager.create_wallet() | 132.227 | 20 |
| TPS 200 appends (labo) | **90.0** | 200 blocs / 2222 ms |

`scripts/benchmark_performance.py` : IR encode/decode + SHA-256 FFI C + PoL (logs `logs/benchmark_*.log` juillet 2026). **Ne pas publier 90 TPS comme perf mainnet** : height live = 1, pas de charge WAN, `enable_security=False` sur une partie du labo.

## 6. Pièges (honnêteté bench)

1. **`bandwidth_mbps: 100.0` / classe BONNE** n’est **pas** un speedtest. Si le trafic pendant 0,5–1 s est &lt; 10 Ko, le code **force 100 Mbps** (`hardware.py`). Snapshot boot : souvent `0.0` + classe `MOYENNE`. Pour un bench officiel : iperf3/ping inter-nœuds, pas cet estimateur.
2. **`/metrics` ~760 ms** : il **dort 0,5 s** pour échantillonner le réseau. Ce n’est pas la latence API.
3. **SHA hétérogène** : seul OVH1 est sur `main` `642b0e1` ; n2/n3/n4 encore `f284180` (SSH absent cet agent). Un bench 4 nœuds doit d’abord **homogénéiser le SHA**.
4. **Pas de TPM / GPU / TEE** : grade **E**. Un bench « hardware-assurance » resterait E jusqu’à bare metal (D-046, sim 192).
5. Chaîne **1 bloc** : un TPS public n’a pas de sens tant qu’on n’a pas un scénario d’append **mesuré** (labo isolé ou TX publiques autorisées).

## 7. Protocole proposé pour le bench officiel (pas encore exécuté ici)

1. Homogénéiser git_sha `main` × 4 (keep-book, clés SSH n2/n4 + AWS).
2. Figer SHA + `uname` + `/api/v1/system/hardware` dans un JSON `simulations/<ts>_bench_official/`.
3. Relancer **sur chaque VM** : `python3 -m scripts.bench_artcb_real` (PQC + append) et `python3 scripts/benchmark_performance.py` (IR/C).
4. Mesure WAN : RTT `/health` déjà ~180–200 ms depuis cet agent ; ajouter iperf3 OVH1↔OVH2↔AWS3↔OVH4.
5. Ne **pas** vider `blocks.jsonl`. Ne **pas** retourner `certified_distributed_mainnet`.
6. Publier un rapport numéroté avec SHA, n, min/med/max, machine — jamais un seul « TPS magique ».

## Interdits respectés

- Pas d’invention de solde, de bloc, de SHA.
- Pas de wipe genèse.
- Pas de `certified=true`.
- Token non affiché.
