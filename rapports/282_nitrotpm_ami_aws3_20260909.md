# 282 — NitroTPM AMI aws-node-3, quote L3 vérifiée

Horodatage live : 2026-09-09T11:01:00Z (quote) / cut-over artcb ensuite  
SHA ×4 : `d5e0c66441714faa251269ca8779f19b2bc9ad80`  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**  
Livre : **1133** lignes, non wipe.  
N04 50 % : **FAIL, dernier**, non rejoué.

L’opérateur a demandé d’**exécuter** NitroTPM : nouvelle AMI UEFI+TPM, ou installer le nécessaire. Guest **swtpm n’a pas** été lancé. L4 matériel n’est **pas** revendiqué.

## Ce qui a été fait (environnement actuel)

1. Clés EC2 depuis Doppler **artcb3** (les alias Cursor `AWS_API_KEY_AGENT_3` étaient `InvalidClientTokenId`).
2. Instance source `i-085b74abd1aaf04ee` : **déjà UEFI** (`/sys/firmware/efi`, `/boot/efi`). `TpmSupport` instance = null.
3. Installé `tpm2-tools` sur la source (pas un quote). `tpm2-abrmd` désactivé sans device.
4. Snapshot `snap-0621d1c686307f311` (vol-00f3d4e427314f47c, 30 GiB, completed).
5. `RegisterImage` **`ami-0b82a9f93189c018e`** : `BootMode=uefi` `TpmSupport=v2.0` (ASCII only).
6. Launch **t3.small** `i-06c9404e42798ff76` eu-west-3a, user-data : artcb **disabled** (pas un second replica).
7. EIP `eipalloc-0009cc00cac2e4cba` → **`13.38.209.25`**.
8. Quote live : manufacturer **AMZN** / vendor **NitroTPM v1.0** ; `tpm2_quote` + `tpm2_checkquote` **verified=true**, kind=`vtpm`.
9. Cut-over : stop artcb + **stop** (pas terminate) `i-085b74abd1aaf04ee`. Binding + IPs git mis à jour. DNS zone `artcb.me` record `n3` PUT → `13.38.209.25` (refresh OK ; cache résolveur encore `51.44.222.232` au moment du dig).

## Live `platform-attest` après cut-over

SHA `d5e0c66` ×4.

| Nœud | class | level | overall | quote | crypto | hardware_tpm | certification | pin |
|---|---|---|---|---|---|---|---|---|
| ovh-1/2/4 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | `DEVICE_ABSENT` | NOT_PROVEN | NOT_AVAILABLE | FAIL | N/A |
| aws-node-3 | **`vtpm`** | **3** | **`VTPM_ATTESTED`** | **verified=true** | **PASS** | NOT_AVAILABLE | FAIL | PASS (sous-verdict) |

`certified_hardware_identity=false`. Binding AWS3 `i-06c9404e42798ff76` **verified**.  
`platform_crypto_attestation=PASS` sur AWS3 = quote TPM2 vérifiée. Ce n’est **pas** L4. Ce n’est **pas** CERTIFIED_100. Le pin RSA-2048 reste un sous-verdict distinct.

## Conservé

N04 FAIL last. C04 / wire_bytes / finalité PBFT / CI GitHub : NOT_PROVEN. OVH sans vTPM hyperviseur.

`logs/282_nitrotpm_live.json`  
`scripts/provision_aws_nitrotpm_ami.py`
