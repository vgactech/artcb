# 281 — Quote TPM/vTPM fail-closed sur les 4 VM actuelles

Horodatage live : 2026-09-09T10:34:02Z  
SHA ×4 : `2c9c1d502e0089031ccddc508d477575cdb621c9` (= `origin/main` au run)  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**  
Livre : **1133** lignes, tip `cc0bf8a1053c7ae7…`, non wipe.  
Ingest de ce tour : HTTP **409 equivocation** (attendu, même vue).

L’audit indépendant R280 est **accepté**. R281 ne « élève » pas le niveau de confiance. Il **exécute** le chemin quote TPM2 sur l’environnement **actuel** et le laisse fail-closed.

## Priorité respectée

1. **vTPM / équivalent TPM sur VM** — mesuré sur les 4 nœuds officiels. Pas de machine hors accès. Pas de bare-metal inventé.
2. N04 50 % — **FAIL, dernier**, non rejoué ici.
3. Guest **swtpm n’est pas** un vTPM hyperviseur. `libtss2-tcti-swtpm0` est présent (TCTI) ; aucun daemon swtpm n’a été lancé pour recaster L3.
4. L4 matériel = machines user / serveurs bare-metal **futurs**, pas ces 4 VM.

## Probe SSH ×4 (environnement actuel)

| Nœud | virt | `/dev/tpm0` | `/dev/tpmrm0` | `/dev/nsm` | modules TPM | `tpm2_quote` |
|---|---|---|---|---|---|---|
| ovh-node-1 | kvm (OpenStack Nova, SeaBIOS) | no | no | no | NO_TPM_MOD | no |
| ovh-node-2 | kvm (OpenStack Nova, SeaBIOS) | no | no | no | NO_TPM_MOD | no |
| aws-node-3 | amazon (`t3.small` `i-085b74abd1aaf04ee`) | no | no | no | NO_TPM_MOD | no |
| ovh-node-4 | kvm (OpenStack Nova, SeaBIOS) | no | no | no | NO_TPM_MOD | no |

OVH Public Cloud n’expose pas de vTPM hyperviseur sur ces instances.  
NitroTPM AWS est un drapeau AMI à `RegisterImage` ; **il ne s’active pas** sur l’instance existante. Remplacer `i-085b74abd1aaf04ee` casserait le registre de binding — **non fait**.

## Live `GET /api/v1/consensus/platform-attest` ×4

| Nœud | class | level | overall | observed | crypto | hardware_tpm | certification | quote | pin AWS |
|---|---|---|---|---|---|---|---|---|---|
| ovh-node-1 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | PASS | NOT_PROVEN | NOT_AVAILABLE | FAIL | `DEVICE_ABSENT` `verified=false` | N/A |
| ovh-node-2 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | PASS | NOT_PROVEN | NOT_AVAILABLE | FAIL | `DEVICE_ABSENT` `verified=false` | N/A |
| aws-node-3 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | PASS | NOT_PROVEN | NOT_AVAILABLE | FAIL | `DEVICE_ABSENT` `verified=false` | **PASS** (sous-verdict) |
| ovh-node-4 | `cloud_instance_identity` | 2 | `CLOUD_ATTESTED` | PASS | NOT_PROVEN | NOT_AVAILABLE | FAIL | `DEVICE_ABSENT` `verified=false` | N/A |

`quote_kind=vtpm` dans le JSON signifie **chemin VM** (L3 *si* quote vérifiée). Ce n’est **pas** « vTPM présent ». L’autorité est `reason=DEVICE_ABSENT` + `verified=false`. Aucun nœud n’est `VTPM_ATTESTED` / L3 / L4.

`honesty_guard=PASS` : pas de recast cloud→TPM, pas de L3 avec DEVICE_ABSENT, `certified_hardware_identity=false` ×4.

## Ce que R281 a réellement ajouté

Chemin `attempt_attestation_quote` :

```
/dev/tpm0 absent → DEVICE_ABSENT (live ×4)
sinon EK/AK → tpm2_quote PCR sha256:0,1,7 + qualifier = node_binding[:32]
→ tpm2_checkquote
VM + device + quote verified = L3, jamais L4
quote_present() exige verified is True (un dict d’échec n’est pas une quote)
```

Tests locaux : `tests/test_e2e281_vtpm_quote.py` + `test_e2e279_platform_trust_sizes.py` — **16 passed**.

## CI GitHub — toujours NOT_PROVEN

SHA `2c9c1d5…` : Combined Status `pending` / `total_count=0`. Aucun workflow run associé.  
`tests.yml` = `workflow_dispatch` only. **PR/merge ≠ CI PASS.** Même lecture que l’audit R280 pour `cc438c2`.

## Conservé (non recasté)

| Élément | Verdict |
|---|---|
| platform_level_observed | PASS (classification + binding) |
| platform_crypto_attestation | NOT_PROVEN |
| hardware_tpm | NOT_AVAILABLE |
| certification | FAIL |
| AWS3 rsa2048 pin | PASS sous-verdict seulement |
| N04 50 % | FAIL (dernier, non travaillé) |
| C04 milliers | NOT_PROVEN |
| TPM/vTPM quote | NOT_PROVEN (DEVICE_ABSENT, pas un FAIL d’outil) |
| wire_bytes | NOT_PROVEN |
| finalité PBFT | NOT_PROVEN |
| CI GitHub | NOT_PROVEN |
| CERTIFIED_100 | false |

`logs/281_vtpm_quote_20260909T103402Z.json`  
`logs/campaigns/281_20260909T103402Z/` MANIFEST `7c87a911…`
