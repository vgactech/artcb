# 278 — Audit adversarial post-R273 (Issue #77 suite)

Horodatage campagne : 2026-09-09T00:09:08Z  
Reprobe rollback/tamper : 2026-09-09T00:22Z  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**

Le rapport n’est pas la preuve. Les JSON bruts le sont.

## Verdicts séparés (ne pas lire `payload.ok`)

`payload.ok` est **null / déprécié**. Il ne signifie pas CERTIFIED_100.

| Champ | Verdict | Preuve |
|---|---|---|
| PRE_R273 A3 GAP | **conservé** | SHA `d9eba2ac` : 200 `not_accepted` |
| POST_R273 A3/A7 | **PASS** | 409 `invalid_replica_key_binding` ×3 sur `d621244` |
| A4 révocation live | **PASS** | overlay sur ovh-4 → 409 `replica_key_revoked` |
| A5 expiration live | **PASS** | overlay → 409 `replica_key_expired` |
| A6 downgrade PQC live | **PASS** | overlay `require_pqc` → 409 `replica_pqc_downgrade` |
| A8 rotation ancienne clé | **PASS** | overlay nouvelle ed → 409 binding pour K2 |
| registry JSON corrompu | **PASS** | overlay `invalid_json`, non appliqué |
| registry rollback v30→v29 | **PASS** (reprobe `6715b6f`) | `overlay_rollback_rejected` ; 1er run `d621244` = **FAIL** (version non persistée) |
| official_node tamper | **PASS** (reprobe) | fichier=`ovh-node-2`, env ombre, id parlé=`ovh-node-4` |
| reboot ovh-2 | **PASS** | height 1133, view 15, id inchangé |
| crash replica ovh-2 | binding **PASS** ; recovery 1er snap **FAIL** | 409 ×3 pendant l’arrêt ; health ovh-2 encore null à +6 s ; ensuite UP |
| NEW-VIEW 1/2/3 | **PASS** (campagne 277, SHA `41c9e1dd`) | analyse seule, pas un NEW-VIEW de vue réelle |
| N04 50 % | **FAIL** | 409 `not_primary` |
| loss 10 % / 100 ms / reorder | **FAIL** | même `not_primary` — le coordinateur a proposé sur ovh-1, primary = ovh-4 |
| TPM quote | **NOT_PROVEN** | `/dev/tpm0` absent ×4 |
| analog cloud | **mesuré** | `platform_class=cloud_instance_identity` ×4 |
| C04 milliers | **NOT_PROVEN** | non exécuté |
| clone NodeID | **NOT_PROVEN** | 2e VM non lancée |

## TPM : ce qui est réellement possible sur ces serveurs

Ce ne sont **pas** des bare-metal. Inventer un quote serait un mensonge.

| Nœud | virt | TPM | Analog le plus proche |
|---|---|---|---|
| ovh-node-1 | kvm | ABSENT | metadata OpenStack/OVH uuid `f2642e42-…` |
| ovh-node-2 | kvm | ABSENT | uuid `6470522e-…` |
| aws-node-3 | amazon | ABSENT | IMDS `i-085b74abd1aaf04ee` **t3.small** eu-west-3 |
| ovh-node-4 | kvm | ABSENT | uuid `22dc6a47-…` |

`GET /api/v1/consensus/platform-attest` expose les deux chemins :

- **tpm_hardware** si `/dev/tpm0` (utilisateurs bare-metal) ;
- **cloud_instance_identity** sur ces VM.

Cloud identity ≠ TPM. `certified_hardware_identity=false`.

## official_node n’est pas la preuve

`ARTCB_NODE_ID` dans le service **prime** sur le fichier. Pendant le tamper :

```
file = ovh-node-2
env  = ovh-node-4
parlé = ovh-node-4   ← propriétaire de la clé K4
```

Le nœud n’a pas parlé en Node2. L’env masque le fichier (`env_shadows_file=true`). C’est une frontière de confiance restante : un attaquant qui change **l’env systemd** + le fichier + la clé est un autre problème (vol de clé).

## A4–A8 : test réel de l’API, pas une simulation hors process

L’overlay `/etc/artcb/replica_overlay.json` est relu au mtime par le process **artcb déjà lancé** sur ovh-4. Les 409 viennent de `POST /pbft/prepare` live.

Le 1er rollback a échoué parce que le process ne pouvait pas écrire le fichier de version. Correctif `6715b6f` : version **en mémoire** (monotone) + disque best-effort. Reprobe : v29 rejeté.

## Chaîne mesurée

SHA campagne `d621244` ×4 puis reprobe `6715b6f` ×4 = `origin/main`.  
Height **1133** tip `cc0bf8a1…` view **15** primary ovh-node-4 `chain_valid` ×4.  
Livre non vidé.

## Artefacts

- `logs/278_adversarial_20260909T000908Z.json`
- `logs/278_adversarial_latest.json`
- `logs/278_reprobe.json`
- `logs/campaigns/278_20260909T000908Z/`

**PBFT 100 % = NON CERTIFIÉ.**
