# 279 — Platform Trust L0–L4 + tailles réelles du livre

Horodatage live : 2026-09-09T00:50:11Z  
SHA déployé ×4 : `5e0d424e0cee85466b44fc163761c2cbda98a855` = `origin/main` de ce run  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**

Le rapport n’est pas la preuve. Les JSON le sont :
`logs/279_trust_sizes_20260909T005011Z.json`,
`logs/279_book_audit.json`,
`logs/campaigns/279_20260909T005011Z/` MANIFEST `19b8c544…`.

Ingest du prompt de ce tour : **409 equivocation** (non gravé). Cursor n’injecte pas le prompt.

## Ce qui change (architecture)

TPM n’est **pas** le système d’identité. C’est **une** racine parmi plusieurs.

| Niveau | Preuve complétée | Verdict global | `certified_hardware_identity` |
|---|---|---|---|
| L4 | TPM matériel + quote | `TPM_ATTESTED` | true |
| L3 | vTPM + quote | `VTPM_ATTESTED` | false |
| L2 | identité cloud (AWS IMDS / OVH metadata) | `CLOUD_ATTESTED` | false |
| L1 | VM observée, pas de doc fournisseur | `VM_UNATTESTED` | false |
| L0 | rien | `UNKNOWN` | false |

Deux verdicts indépendants :

- `hardware_tpm_attestation` — sur ces 4 VM : **`NOT_AVAILABLE`**
- `platform_identity_attestation` — **`OVH_CLOUD_ATTESTED`** / **`AWS_CLOUD_ATTESTED`**

`CLOUD_ATTESTED` n’est **jamais** recasté en `TPM_ATTESTED`.
`/dev/tpm0` absent n’est **pas** « NODE IDENTITY = NOT_PROVEN ».

PKCS#7 AWS et metadata OVH : documents collectés, **signatures non vérifiées contre les CA** (`attestation_crypto_verified=false`). Ne pas lire L2 comme une quote TPM.

## Live ×4 après `5e0d424`

| Nœud | class | L | overall | hardware TPM | platform | instance | binding |
|---|---|---|---|---|---|---|---|
| ovh-node-1 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | `NOT_AVAILABLE` | `OVH_CLOUD_ATTESTED` | `f2642e42-323c-4621-b0e8-a82ffb20f184` | verified |
| ovh-node-2 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | `NOT_AVAILABLE` | `OVH_CLOUD_ATTESTED` | `6470522e-1561-4741-9254-5f58b909eeb9` | verified |
| aws-node-3 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | `NOT_AVAILABLE` | `AWS_CLOUD_ATTESTED` | `i-085b74abd1aaf04ee` t3.small | verified |
| ovh-node-4 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | `NOT_AVAILABLE` | `OVH_CLOUD_ATTESTED` | `22dc6a47-5b79-4084-82d7-eabb4f5b2680` | verified |

`recast_cloud_as_tpm=false`. `identity_mismatch=0`.

Quatre identités restent séparées : NodeID logique (label) ≠ machine-id/DMI ≠ instance fournisseur ≠ racine TPM/vTPM.  
`ARTCB_NODE_ID` / `/etc/artcb/official_node` ne peuvent pas réécrire l’instance. Un env `ovh-node-4` sur l’UUID de ovh-2 → `IDENTITY_MISMATCH` (test unitaire). Live : pas de mismatch.

## Livre réel `blocks.jsonl` (ovh-1, pas inventé)

Fichier : `/home/ubuntu/artcb/data/chain/blocks.jsonl`  
**1133 lignes**, index **0 … 1132**, `file_bytes=10 339 579` (~9,86 MiB).  
height 1133 = 1133 enregistrements (genesis index 0). Livre **non wipe**.

| Mesure | Valeur live |
|---|---|
| `line_bytes` min | **7496** |
| p50 | **7597** |
| p90 | 7600 |
| p95 | 7730 |
| p99 | 46727 |
| max | **47192** |
| avg | 9124 |
| stdev | 7502 |
| somme line_bytes | 10 338 446 (82 707 568 bits) |
| buckets API (`file_bytes` + newline) | 1088 × 1–10 KB ; 45 × 10–100 KB ; 0 × >100 KB |

Les chiffres documentaires historiques **622 B / ~28 Ko / 665 Ko ne sont pas ce livre**. Ne pas les substituer.

`claimed_block_size_bytes` ≠ `line_bytes` sur **1133/1133** blocs.

Deux causes, mesurées :

1. **Champ calculé avant lui-même.** Genesis : claimed 7708 = `payload_bytes` ; line 7732 (+24). C’est le `json.dumps` sans le champ, puis insertion.
2. **`pbft_cert` ajouté après.** Blocs 1130/1131 : line **47192**, claimed **7738**. Le certificat (~39431 octets) n’était pas dans la mesure. Le hash ne contient pas `pbft_cert` (sidecar) — la taille fichier si.

`to_json_line()` converge désormais. `import_extending_block` reconverge **après** attache du certificat. Les 1133 lignes existantes **ne sont pas réécrites**.

Quatre tailles (ne pas les confondre) :

| Nom | Ce run |
|---|---|
| `payload_bytes` | JSON utile sans le champ taille |
| `line_bytes` | JSON UTF-8 sans newline |
| `file_bytes` / `file_record_bytes` | ligne + `\n` (offsets `/block-sizes`) |
| `wire_bytes` | **non mesuré** (HTTP/TLS/TCP/IP) |

TX / Jobs / Proofs / WorkUnits **par bloc** : non extraits (pas inventés). Contributors et clés `public_symbols` seulement.

## Temps inter-blocs (timestamps du livre)

1132 intervalles : min 0 s, **p50 = 1,0 s**, moyenne **549 s**, max **327016 s** (trou genesis 2026-09-01 → premier bloc 2026-09-05).

**1 s/bloc = médiane des Δt gravés, pas une finalité réseau.**  
Pas de décomposition production / propagation / consensus / finalité dans ce run.

22,61 TPS : benchmark historique d’un scénario — **pas** une capacité universelle. Non rejoué ici.

## Head / tail (préfixes de hash seulement)

| index | ts | line | claimed | hash[:16] |
|---:|---|---:|---:|---|
| 0 | 2026-09-01T18:34:30Z | 7732 | 7708 | `b8a7d5ef50052790` |
| 1 | 2026-09-05T13:24:46Z | 7753 | 7729 | `5c952df62b0cc2c8` |
| 2 | 2026-09-05T13:24:49Z | 7779 | 7755 | `93eab711365a59c3` |
| 1130 | 2026-09-08T22:58:09Z | 47192 | 7738 | `6cd65457e2722196` |
| 1131 | 2026-09-08T23:06:19Z | 47192 | 7738 | `c152eb6666e40adf` |
| 1132 | 2026-09-08T23:13:23Z | 46725 | 7271 | `cc0bf8a1053c7ae7` |

Plus petit : index 7 = 7496. Plus gros : 1130/1131 = 47192 (`pbft_cert`).

## Ce qui reste (non recasté)

| Item | Verdict |
|---|---|
| PRE_R273 A3 GAP (`d9eba2ac` 200 `not_accepted`) | conservé |
| N04 50 % | **FAIL** |
| C04 thousands | **NOT_PROVEN** |
| TPM quote / PCR / AK | **NOT_PROVEN** (device absent ; chemin bare-metal inchangé) |
| PKCS#7 / metadata CA verify | **non implémenté** |
| WorkUnits / scheduler universel | architecture, pas une mesure live |
| `rollback_attack_rejected` | nom corrigé dans le runner 278 ; attaque rejetée = PASS |
| CERTIFIED_100 | **false** |

T-E64. AWS reste **t3.small** `i-085b74abd1aaf04ee`. HPC interdit. Jamais wipe.
