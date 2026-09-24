# R460 — Liaison cryptographique TPM EK → NodeID (ARTCB-NODE-TPM-BINDING-v1)

**Date :** 2026-09-25  
**SHA HEAD avant commit :** `bc44297`  
**Tâche :** TASK-001-BIOMETRIE-SUITE — Chaînon manquant Niveaux C+D  
**Statut :** ✅ 22/22 tests PASS — `CERTIFIED_100=false`

---

## 1. Contexte et motivation

La session précédente (message utilisateur expert) a effectué une analyse rigoureuse de la chaîne de preuve ARTCB et a identifié **deux niveaux distincts** qui n'étaient pas encore implémentés :

| Niveau | Description | État avant R460 |
|--------|-------------|-----------------|
| A | TPM physique présent (`/dev/tpm0`) | ✅ `hardware_identity.py` |
| B | TPM accessible par ARTCB (EK cert, PCR) | ✅ `probe_tpm2_tools()` + `_read_tpm_ek_cert()` |
| **C** | **NodeID dérivé cryptographiquement du TPM EK** | ❌ absent |
| **D** | **Preuve distante vérifiable par les pairs** | ❌ absent |

La formulation rigoureuse documentée dans la session était :

> *« Certaines machines auditées disposent réellement d'un TPM 2.0 matériel. Il faut démontrer que les nodes ARTCB live sont effectivement exécutés dans ces environnements et que l'identité de node est cryptographiquement liée et attestée par ce TPM. »*

R460 implémente le chaînon manquant : le binding signé `device_fingerprint → NodeID`.

---

## 2. Avant / Après

### Avant R460

```
hardware_identity.py
    └── device_fingerprint = SHA-256(tpm_ek_cert_hash | machine_id | hostname | ...)
                                        ↓
                              stocké dans data/node_device.json
                                        ↓
                              AUCUN lien signé vers le node_id P2P
```

Le `device_fingerprint` était calculé et persisté, mais aucune preuve cryptographique ne liait ce fingerprint à l'identité P2P du nœud.

### Après R460

```
hardware_identity.py                    src/artcb/security/node_tpm_binding.py
    └── device_fingerprint ─────────→  create_node_tpm_binding(
                                            node_id="node-ovh2",
                                            ed25519_signing_key_bytes=...,
                                            device_fingerprint=...,
                                            hardware_assurance_level="B",  ← jamais inventé
                                            tpm_ek_cert_hash=...,
                                        )
                                            ↓
                                        NodeTpmBinding (signé Ed25519 [+ ML-DSA-65])
                                            ↓
                                        verify_node_tpm_binding(binding, expected_node_id=...)
                                            ↓
                                        BindingVerificationResult.valid = True/False
```

---

## 3. Fichiers créés/modifiés

| Fichier | Action | Lignes |
|---------|--------|--------|
| `src/artcb/security/node_tpm_binding.py` | **CRÉÉ** | 497 |
| `tests/test_r460_node_tpm_binding.py` | **CRÉÉ** | 290 |

---

## 4. Architecture du module

### Protocol : `ARTCB-NODE-TPM-BINDING-v1`

```python
# Payload signé (canonique JSON sorted_keys)
{
  "protocol": "ARTCB-NODE-TPM-BINDING-v1",
  "node_id": "node-ovh2",
  "device_fingerprint": "<sha256-64hex>",
  "hardware_assurance_level": "B",     # A|B|C|D|E
  "hardware_kind": "virtual_tpm",
  "tpm_ek_cert_hash": "<sha256-64hex | null>",
  "tpm_kind": "virtual",               # physical|virtual|absent
  "platform_system": "Linux",
  "env_type": "linux_headless",
  "nonce": "<64hex — anti-rejeu>",
  "timestamp": "2026-09-25T..."
}
```

### Niveaux de garantie (D-045 — jamais inventer une puce)

| Niveau | hardware_kind | tpm_proven | Condition |
|--------|--------------|-----------|-----------|
| A | `physical_tpm` | **True** | `/dev/tpm0` + non-VM + EK cert hash |
| B | `virtual_tpm` | **True** | `/dev/tpm0` + VM + EK cert hash |
| C | `tee` | False | SEV/SGX/TDX détecté |
| D | `hsm` | False | `ARTCB_HSM_BINDING=true` |
| E | `software` | False | machine-id seulement |

### Invariants

```python
tpm_proven = hardware_assurance_level in {"A", "B"} and tpm_ek_cert_hash is not None
certified = False           # ABSOLU — jamais modifiable
unique_human_proven = False # ce module ne prouve pas l'unicité humaine
```

### Signature

- **Ed25519** : toujours présente (D-032 — toujours actif)
- **ML-DSA-65** : optionnelle — si `liboqs` disponible (D-032 hybride)
- **hybrid_and** : `True` ssi les deux signatures présentes et vérifiées (D-034)

---

## 5. Résultats des tests

```
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-9.1.1
collected 22 items

tests/test_r460_node_tpm_binding.py ......................  [100%]

============================== 22 passed in 0.45s ==============================
```

### Matrice des scénarios

| Test | Scénario | Résultat |
|------|----------|----------|
| T01 | Niveau A : binding créé sans exception | ✅ PASS |
| T02 | Niveau A + EK → tpm_proven=True | ✅ PASS |
| T03 | Niveau B (vTPM) + EK → tpm_proven=True | ✅ PASS |
| T04 | Niveau C (TEE) → tpm_proven=False | ✅ PASS |
| T05 | Niveau D (HSM) → tpm_proven=False | ✅ PASS |
| T06 | Niveau E (software) → tpm_proven=False | ✅ PASS |
| T07 | node_id vide → ValueError | ✅ PASS |
| T08 | device_fingerprint vide → ValueError | ✅ PASS |
| T09 | Vérification OK même NodeID → valid=True | ✅ PASS |
| T10 | NodeID mismatch → valid=False + failure_reason | ✅ PASS |
| T11 | Falsification device_fingerprint → valid=False | ✅ PASS |
| T12 | Falsification hardware_assurance_level (E→A) → valid=False | ✅ PASS |
| T13 | Falsification tpm_ek_cert_hash → valid=False | ✅ PASS |
| T14 | certified=False absolu | ✅ PASS |
| T15 | unique_human_proven=False absolu (tous niveaux) | ✅ PASS |
| T16 | to_dict() round-trip complet | ✅ PASS |
| T17 | Niveau A sans EK cert → tpm_proven=False | ✅ PASS |
| T18 | require_tpm_proven=True + niveau E → valid=False | ✅ PASS |
| T19 | require_tpm_proven=True + niveau A + EK → valid=True | ✅ PASS |
| T20 | Nonce différent à chaque create (anti-rejeu) | ✅ PASS |
| T21 | Signature Ed25519 incorrecte → valid=False | ✅ PASS |
| T22 | BindingVerificationResult.to_dict() structure complète | ✅ PASS |

### Non-régression

```
tests/test_task001_r374_bch.py            30 passed
tests/test_task001_r376_uniqueness.py     22 passed
tests/test_task001_r373_human_identity_policy.py  26 passed
Total : 78/78 PASS — zéro régression
```

---

## 6. Propriétés de sécurité démontrées

1. **Anti-falsification** : toute altération de `device_fingerprint`, `hardware_assurance_level` ou `tpm_ek_cert_hash` après signature invalide la vérification (T11/T12/T13).

2. **Anti-élévation** : un nœud niveau E (software) ne peut pas se déclarer niveau A (TPM) sans invalider sa signature (T12).

3. **Anti-rejeu** : nonce 32 octets aléatoires, différent à chaque binding créé (T20).

4. **Fail-closed** : vérification → false si Ed25519 invalide, NodeID mismatch, ou contrainte TPM/hybride non satisfaite.

5. **Invariants absolus** : `certified=False` et `unique_human_proven=False` non modifiables après création (T14/T15).

---

## 7. Limites honnêtes

- **Niveau C+D partiellement adressé** : ce module implémente la liaison signée `device_fingerprint → NodeID`. La *propagation* de cette preuve aux autres nœuds via P2P (Niveau D complet) reste à faire — le binding est un artefact local signé, pas encore diffusé dans le réseau P2P.

- **tpm_proven ≠ quote TPM** : `tpm_proven=True` signifie que le EK cert hash était présent au moment de la création du binding. Une quote TPM complète (PCR + nonce signé par AK) est la prochaine étape (nécessite `tpm2-tools` + accès `/dev/tpmrm0`).

- **Vecteurs synthétiques** : les tests utilisent des fingerprints et EK hashes simulés. Les tests live nécessitent un environnement avec `/dev/tpm0` réel.

- **`CERTIFIED_100=false`** : aucune certification automatique.

---

## 8. Prochaines étapes TASK-001

| Priorité | Chantier | Description |
|----------|----------|-------------|
| P0 | R461 — Diffusion P2P du binding | `POST /p2p/node-tpm-binding` : propager `NodeTpmBinding.to_dict()` aux pairs + vérification à la réception |
| P1 | R462 — Quote TPM PCR (si `/dev/tpm0` disponible) | Intégrer `probe_tpm2_tools().pcr0_sha256` dans le payload signé |
| P2 | FHE véritable | SEAL/OpenFHE/Concrete pour `check_uniqueness()` — remplacer simulation `FheHammingCircuit` |

---

## 9. Chaîne de preuve — État après R460

```
HUMAIN → WebAuthn → Wallet → Device → TPM EK/AK → NodeID → P2P → Blockchain
                                  ↑
                          [R460 ici]
                   device_fingerprint (hardware_identity.py)
                          ↓
                   NodeTpmBinding signé Ed25519
                          ↓
                   verify_node_tpm_binding() — fail-closed
```

`CERTIFIED_100=false`
