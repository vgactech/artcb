# 284 — Classification honnête (Phase A)

Horodatage live PASS : 2026-09-09T16:11:06Z  
SHA ×4 : `b848428899d3c209a551299414e03e8beef15107` = `origin/main`  
CERTIFIED_100 : **false**  
PRODUCTION_READY : **false**  
Livre : **1133**, non wipe.  
N04 50 % : **FAIL, dernier**, non rejoué.  
PRE_R273 K1→Node2 : **GAP conservé**, pas un PASS rétroactif.  
CI GitHub : **NOT_PROVEN**.  
Mac `10.234.49.2` : **NOT_REACHABLE** depuis ce VM cloud (RFC1918). Aucune clé SSH ni mot de passe n’a été écrit dans git.

R283 a corrigé le gate L4 universel. R284 corrige les bugs de **deuxième génération** de classification.

## Politique `284-environment-classification`

- `UNKNOWN ≠ BARE_METAL` (`environment_certainty`).
- Kinds TPM : `HARDWARE_TPM` / `HYPERVISOR_VTPM` / `NITROTPM` / `SOFTWARE_TPM` / `UNKNOWN_TPM` / `ABSENT`.
- `/dev/tpm0` seul **n’est pas** L3. swtpm **jamais** L3.
- `maximum_theoretical_level` ≠ `maximum_verified_level`.
- `CERTIFIED_100` = PASS applicables / applicables. `NOT_APPLICABLE` hors dénominateur. `NOT_REACHABLE` n’est pas satisfait.
- L2 précis : `CLOUD_IDENTITY_OBSERVED`.
- Fraîcheur : `LOCAL_GENERATED` ≠ challenge vérificateur.
- `missing_requirements` listé. `policy_hash` = `08753095e8baf74c4fe6dddf26873a8c71773559040bec2c7f9b39afe29cea3c`.

## Live ×4 (SHA `b848428`)

| Nœud | certitude | profil | tpm_kind | theo | verified | attested | l3 | l4 | profil cert | raw_hash |
|---|---|---|---|---|---|---|---|---|---|---|
| OVH1/2/4 | VM_PROVEN | CLOUD_VM | ABSENT | 2 | 2 | 2 | NOT_REACHABLE | NOT_APPLICABLE | PASS | voir JSON |
| AWS3 | VM_PROVEN | CLOUD_VM_VTPM | **NITROTPM** | 3 | 3 | 3 | PASS | NOT_APPLICABLE | PARTIAL | `9a378a5c…` |

AWS3 `missing_requirements` = `["ek_ak_provenance"]`. Quote signature PASS. Freshness `LOCAL_GENERATED`. `certified_hardware_identity=false`.

## Retry / échecs enregistrés (provenance)

1. `logs/284_classify_20260909T160748Z.json` — parser getcap tronqué (queue 500 o) → AWS3 `UNKNOWN_TPM` malgré quote verified. **Correct fail-closed**, puis fix `keep=4000` tête de `tpm2_getcap`.
2. `logs/284_classify_20260909T161026Z.json` — follow-main, OVH2/4 health pas encore UP (`sha=""`, OVH4 attest vide). Retry.
3. `logs/284_classify_20260909T161106Z.json` — PASS classification. Ledger `logs/284_agent_run_20260909T161106Z.json` tip `e583553c…`.

## Non fait

Challenge nonce vérificateur, chaîne EK fabricant, binding quote indépendant du registre, provenance agent complète (thinking privé non enregistré ; hashes seulement), N04, C04, finalité PBFT, machine Mac locale.

`logs/284_classify_live.json`  
`logs/campaigns/284_20260909T161106Z/`  
`scripts/run_live284_classify.py`
