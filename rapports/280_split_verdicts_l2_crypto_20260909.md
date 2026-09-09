# 280 — Verdicts séparés : observé ≠ crypto ≠ certification

Horodatage live : 2026-09-09T01:34:17Z  
SHA ×4 : `0d7546c09ddd3b5f3ce3235d6ed69927263ea4bf`  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**  
Livre : **1133** lignes, non wipe.

L’audit indépendant de R279 est **accepté**. R280 ne « corrige » pas R279 : il empêche de lire un `PASS` de classification comme une attestation CA.

## Formulation retenue

L2 `CLOUD_ATTESTED` = identité de plateforme **observée** + binding registre.  
Ce n’est **pas** une quote TPM. Ce n’est **pas** encore :

```
document signé → CA → fraîcheur/challenge → liaison Ed25519 → anti-rejeu
```

`attestation_crypto_verified` reste **false** tant qu’il n’y a pas de quote TPM/vTPM.

## Live `split_verdicts` ×4

| Nœud | observed | crypto | hardware_tpm | certification | aws_iid_rsa2048_pin |
|---|---|---|---|---|---|
| ovh-node-1 | PASS | NOT_PROVEN | NOT_AVAILABLE | FAIL | NOT_APPLICABLE |
| ovh-node-2 | PASS | NOT_PROVEN | NOT_AVAILABLE | FAIL | NOT_APPLICABLE |
| aws-node-3 | PASS | NOT_PROVEN | NOT_AVAILABLE | FAIL | **PASS** (pin eu-west-3) |
| ovh-node-4 | PASS | NOT_PROVEN | NOT_AVAILABLE | FAIL | NOT_APPLICABLE |

Sur AWS3, `openssl smime -verify -noverify` contre le certificat RSA-2048 **publié** pour eu-west-3 a réussi (`rsa2048_pin.verified=true`). C’est un **pin documenté par AWS**, pas une marche CA publique, pas de nonce/challenge, pas de liaison à la clé Ed25519 du nœud. **Ce PASS n’élève pas** `platform_crypto_attestation` ni `certified_hardware_identity`.

OVH : metadata toujours non signée ici → pin N/A, crypto NOT_PROVEN.

## Conservé

N04 50 % FAIL. C04 / quote TPM NOT_PROVEN. `honesty_guard=PASS` (aucun recast cloud→TPM, aucun `certification=PASS` fuite).

Ingest de ce tour : 409 equivocation.

`logs/280_split_verdicts_20260909T013417Z.json`  
`logs/campaigns/280_20260909T013417Z/`
