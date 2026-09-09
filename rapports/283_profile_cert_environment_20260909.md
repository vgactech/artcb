# 283 — Certification par profil d’environnement (L4 n’est pas une exigence universelle)

Horodatage live : 2026-09-09T14:30:29Z  
SHA ×4 : `667742087f143b6a0271f3075da2fdf58c539dd6` = `origin/main`  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**  
Livre : **1133** lignes, non wipe.  
N04 50 % : **FAIL, dernier**, non rejoué.  
CI GitHub : **NOT_PROVEN** (`workflow_dispatch` only).

Le rapport R282 a classé AWS3 **L3 `VTPM_ATTESTED`** (NitroTPM quote vérifiée) tout en laissant `certification=FAIL` parce que le code **codait FAIL en dur** en attendant un TPM matériel. C’était une erreur de conception : une VM ne peut pas fournir L4.

## Politique corrigée

```text
ENVIRONNEMENT → CAPACITÉS → NIVEAU MAXIMAL → PREUVES REQUISES → VALIDATION → CERTIFICATION
```

Pas : « tout le monde doit satisfaire L4 ».

| Axe | Signification |
| --- | --- |
| `environment` | `CLOUD_VM` / `VM` / `BARE_METAL` |
| `maximum_supported_level` | maximum techniquement atteignable |
| `attested_level` | niveau effectivement démontré |
| `profile_certification` | PASS / PARTIAL / NOT_PROVEN / FAIL contre **ce** profil |

`CERTIFIED_100` = 100 % des exigences **applicables au profil détecté**, pas 100 % du niveau matériel maximal imaginable.

L4 sur une VM = **`NOT_APPLICABLE`**, pas `FAIL`.  
L3 sur OVH sans vTPM hyperviseur = **`NOT_REACHABLE`**.  
L3 n’est **jamais** L4. `certified_hardware_identity` reste vrai seulement en L4 quote matériel vérifiée.

## Live `GET /api/v1/consensus/platform-attest` ×4

Protocole `283-environment-profile-attestation`. SHA `6677420` ×4.

| Nœud | env | profil | max | observé | l3 | l4 | quote | freshness | EK | binding quote | certification profil | CERTIFIED_100 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ovh-1/2/4 | `CLOUD_VM` | `CLOUD_VM` | **2** | **2** `CLOUD_ATTESTED` | `NOT_REACHABLE` | `NOT_APPLICABLE` | `DEVICE_ABSENT` | N/A | N/A | N/A | **PASS** | false |
| aws-node-3 | `CLOUD_VM` | `CLOUD_VM_VTPM` | **3** | **3** `VTPM_ATTESTED` | **PASS** | `NOT_APPLICABLE` | **verified** kind=`vtpm` | **PASS** | **NOT_PROVEN** (`LOCAL_CREATEEK`) | **PASS** | **PARTIAL** | false |

`hardware_tpm_attestation=NOT_APPLICABLE` ×4.  
`certified_hardware_identity=false` ×4.  
OVH n’est **pas** pénalisé pour l’absence de NitroTPM.  
AWS3 n’est **pas** L4.

AWS3 L3 = quote TPM2 vérifiée + nonce de fraîcheur mixé dans le qualifier (16 octets binding + 16 octets nonce) + préfixe de binding nœud. Ce n’est **pas** une certification complète du nœud : la provenance fabricant EK/AK n’est pas démontrée (`tpm2_createek` local). D’où **PARTIAL** et `CERTIFIED_100=false` **pour cette raison**, pas parce que L4 est absent.

## Conservé

N04 FAIL last. C04 / wire_bytes / finalité PBFT : NOT_PROVEN. Guest swtpm non lancé. Instance AWS3 `i-06c9404e42798ff76` inchangée. Known_hosts SSH AWS3 mis à jour (nouvelle instance R282).

`logs/283_profile_cert_live.json`  
`logs/283_profile_cert_20260909T143029Z.json`  
`logs/campaigns/283_20260909T143029Z/`  
`scripts/run_live283_profile_cert.py`
