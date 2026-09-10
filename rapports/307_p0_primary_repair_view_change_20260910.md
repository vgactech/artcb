# R307 — P0 repair : primary_of + VIEW-CHANGE/NEW-VIEW (sans wipe)

**UTC :** 2026-09-10T15:50:00Z  
**CERTIFIED_100 :** `false` (maintenu)  
**wipe :** `false`

## Verdict opérateur (confirmé)

Continuité du livre 4 seeds ≠ consensus BFT N=5 certifié.  
`409` sur propose ambigu = **protection**, pas corruption.  
Ordre retenu : SHA×5 → règle canonique primary → VC/NV → PREPARE/COMMIT Q=3 → Mac tunnel → chaos.

## Règle canonique (P0-B)

**Normative :** `primary_of(view)` sur `official_pbft_replica_ids()` (N=5).  
**Non normative :** `primary` stocké dans `pbft_view.json` s’il diverge.

| view | primary_of |
|------|------------|
| 15 | ovh-node-1 |
| 16 | ovh-node-2 |
| 17 | aws-node-3 |

Exemple audit « view 16 → OVH1 » = **incorrect** sous N=5 ; le protocole donne **ovh-node-2**.

## P0-A — SHA ×5

Target = `origin/main` au run de réparation : `8acbbdee060a0c0c81e186d4e2b6fe5cd022581c`.

| node | git_sha (health) | note |
|------|------------------|------|
| OVH1 | `8acbbdee…` | PASS |
| OVH2 | `8acbbdee…` | PASS |
| AWS3 | `8acbbdee…` | rattrapé après reboot EC2 (follow-main hôte) ; avant : `852f0e2…` |
| OVH4 | `8acbbdee…` | PASS |
| Mac | `8acbbdee…` | PASS local `:8001` |

SSH IPv4 AWS3 `13.38.209.25:22/8000/8443` = **Connection refused** (SG autorise `0.0.0.0/0` ; filtre hôte). HTTPS `n3.artcb.me` = 200.  
Doppler `artcb3`/`dev` : `AWS_INSTANCE_ID` / `AWS_SERVER_IP` corrigés → `i-06c9404e42798ff76` / `13.38.209.25` (ex-retired retiré des métadonnées). IAM profile **absent** → SSM indisponible. Serial console account **disabled**.

## P0-B — VIEW-CHANGE / NEW-VIEW

Avant (×4 seeds) : view **15**, stored `ovh-node-4` ≠ `primary_of` `ovh-node-1`.

Réparation 1 : VC → view **16**, NEW-VIEW primary **ovh-node-2**, VC×4, fan-out 200.  
`logs/307_p0_primary_repair.json` : `aligned_seeds=true`.

Réparation 2 (clear PRE-PREPARE orphelin du propose probe) : VC → view **17**, primary **aws-node-3**.

Après : view **17**, stored = `primary_of` = **aws-node-3** ×4 seeds.

## PREPARE / COMMIT Q=3 (seeds)

`logs/307_p0_prepare_commit_probe.json` :

- propose primary aws-node-3 : HTTP **200**, digest `577fff7e…`
- PRE-PREPARE fan-out ×3 followers : 200
- PREPARE **4/4** (≥ Q=3)
- COMMIT **4/4** (≥ Q=3)
- certificat présent ; `wrote=true` ×4
- tip seeds : height **1134**, `last_hash` `577fff7e5982d70a…`

## Tip ×5 / Mac

| node | height | tip |
|------|--------|-----|
| seeds ×4 | 1134 | `577fff7e…` |
| Mac | **6** | `01a5f743…` (livre local distinct) |

Mac : membership JSON n=5 **oui** ; transport PBFT public **NON PROUVÉ** ; tip×5 **FAIL**. Chaos L/M/N **NOT_RUN**.

## Ingest ce tour

`ingest_skipped=true`, HTTP 409 `equivocation` (avant repair) — prompt **pas** on-chain. `includes_thinking=false`.

## Tableau final

| Élément | État |
|---------|------|
| CERTIFIED_100 | **false** |
| SHA ×5 | **PASS** (`8acbbdee…`) |
| Primary alignment seeds | **PASS** (view 17) |
| PREPARE/COMMIT Q=3 seeds | **PASS** |
| Tip seeds | **PASS** height 1134 |
| Tip ×5 (Mac inclus) | **FAIL** |
| Mac PBFT transport | **NOT_PROVEN** |
| Chaos | **NOT_RUN** |
| Wipe | **false** |

## Suite

1. Tunnel public Mac + handshake PREPARE/COMMIT (pas seulement health).  
2. Puis seulement chaos L/M/N.  
3. Ne pas lever `CERTIFIED_100`.
