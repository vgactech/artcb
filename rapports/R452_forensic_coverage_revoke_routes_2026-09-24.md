# R452 — Forensic Coverage Complète : revoke_with_history + routes biométriques

**Date :** 2026-09-24  
**SHA commit :** `99c9259`  
**Branche :** `main` (origin/main)  
**CERTIFIED_100 :** false  
**Avancement ARTCB :** ~52 % (inchangé — R452 ne certifie pas de fonctionnalité nouvelle)

---

## Contexte

R451 avait implémenté le `ForensicEventLedger` (hash-chain + Merkle root) et l'avait branché sur :
- `biometric_onchain.py` : enroll + check_uniqueness
- `reasoning/pipeline.py` : 6 événements/run

L'audit R452 (L-055 appliqué — lecture des fichiers HEAD avant déclaration) a révélé que **3 modules critiques manquaient de couverture forensic** :

| Chemin critique | Avant R452 | Après R452 |
|---|---|---|
| `biometric_identity_routes.py` — enroll nominal | ❌ | ✅ `BIO_ENROLL_OK/SUCCESS` |
| `biometric_identity_routes.py` — unicité refusée | ❌ | ✅ `BIO_ENROLL_FAIL/REJECTED` |
| `biometric_identity_routes.py` — store inaccessible | ❌ | ✅ `SYBIL_STORE_UNAVAILABLE` |
| `biometric_identity_routes.py` — sybil bloqué | ❌ | ✅ `SYBIL_CHECK_BLOCKED` |
| `wallet_device_binding.py` — check_and_bind idempotent | ❌ | ✅ `BINDING_CHECK_OK/SUCCESS` idempotent |
| `wallet_device_binding.py` — device déjà lié | ❌ | ✅ `BINDING_CHECK_BLOCKED/REJECTED` |
| `wallet_device_binding.py` — nouveau binding | ❌ | ✅ `BINDING_CHECK_OK/SUCCESS` |
| `wallet_device_binding.py` — revoke MISSING_CRITERIA | ❌ | ✅ `WALLET_REVOKE_FAIL/REJECTED` |
| `wallet_device_binding.py` — revoke BINDING_NOT_FOUND | ❌ | ✅ `WALLET_REVOKE_FAIL/REJECTED` |
| `wallet_device_binding.py` — revoke ALREADY_REVOKED | ❌ | ✅ `WALLET_REVOKE_FAIL/REJECTED` |
| `wallet_device_binding.py` — revoke CAS_VERSION_CONFLICT | ❌ | ✅ `WALLET_REVOKE_FAIL/REJECTED` |
| `wallet_device_binding.py` — revoke nominal | ❌ | ✅ `WALLET_REVOKE_OK/SUCCESS` |

---

## Fichiers modifiés

### 1. `src/artcb/security/wallet_device_binding.py`

**Avant R452 :** `MODULE_VERSION = '1.3.1'`  
**Après R452 (post-hook bump) :** `MODULE_VERSION = '1.3.4'`

**Ajouts :**

#### Wrapper `_emit()` (ligne 68)
```python
# AVANT — n'existait pas
# APRÈS
def _emit(event_type_name: str, outcome_name: str, ctx_name: str, **kwargs) -> None:
    """Wrapper forensic fail-open pour wallet_device_binding."""
    if not _FORENSIC_AVAILABLE:
        return
    try:
        _emit_forensic(
            None,
            event_type=_FET(event_type_name),
            outcome=_AO(outcome_name),
            evaluation_context=_EC(ctx_name),
            layer="wallet-binding",
            **kwargs,
        )
    except Exception:
        pass  # never block binding operations
```

#### `revoke_with_history()` — 5 points forensic ajoutés

| Point | Condition | EventType | Outcome | failure_reason_code |
|---|---|---|---|---|
| L.494 (avant raise) | `not any([wallet_name, fp, binding_id])` | `WALLET_REVOKE_FAIL` | `REJECTED` | `MISSING_CRITERIA` |
| L.525 (avant raise) | `target_idx is None` | `WALLET_REVOKE_FAIL` | `REJECTED` | `BINDING_NOT_FOUND` |
| L.534 (avant raise) | `current_state == REVOKED` | `WALLET_REVOKE_FAIL` | `REJECTED` | `ALREADY_REVOKED` |
| L.542 (avant raise) | `expected_version != current_version` | `WALLET_REVOKE_FAIL` | `REJECTED` | `CAS_VERSION_CONFLICT` |
| L.584 (après logger.warning) | chemin nominal | `WALLET_REVOKE_OK` | `SUCCESS` | — |

**Propriété clé :** tous les `_emit()` sont dans le wrapper fail-open — une exception forensic ne bloque jamais la révocation.

---

### 2. `src/api/biometric_identity_routes.py`

**Avant R452 :** `MODULE_VERSION = '1.0.4'` (pas de forensic)  
**Après R452 (post-hook bump) :** `MODULE_VERSION = '1.0.7'`

**Imports ajoutés :**
```python
# AVANT — absents
# APRÈS
from src.artcb.trace.forensic import (
    AttemptOutcome,
    EvaluationContext,
    ForensicEventType,
    emit_forensic,
)
```

**4 appels `emit_forensic()` ajoutés dans `enroll()` :**

| Ligne | Condition | EventType | Outcome |
|---|---|---|---|
| ~199 | unicité refusée | `BIO_ENROLL_FAIL` | `REJECTED` |
| ~231 | store inaccessible | `SYBIL_STORE_UNAVAILABLE` | `STORE_UNAVAILABLE` |
| ~272 | sybil bloqué | `SYBIL_CHECK_BLOCKED` | `SYBIL_BLOCKED` |
| ~311 | enrôlement réussi | `BIO_ENROLL_OK` | `SUCCESS` |

---

### 3. `tests/test_r452_forensic_coverage_api_binding.py` (NOUVEAU)

**16 tests A01→D04 :**

| Groupe | Tests | Description |
|---|---|---|
| A — revoke_with_history forensic | A01→A05 | 5 chemins d'erreur/succès |
| B — check_and_bind forensic (non-régression) | B01→B03 | idempotent, blocked, success |
| C — biometric_identity_routes (structurel) | C01→C04 | imports, version, source, enroll nominal |
| D — invariants transversaux | D01→D04 | fail-open, module absent, state_after content, version |

---

## Résultats des tests

```
Lot 1 — binding + forensic R452 :     82/82  PASS  (2.41s)
Lot 2 — knowledge + sybil + langues : 127/127 PASS  (3.14s)
Lot 3 — R400-R406 versioning :        71 PASS / 8 FAIL préexistants (non introduits par R452)
Lot 4 — G16 + G4 pipeline :           77/77  PASS  (3.17s)
Lot 5 — task001 biometrie + WebAuthn : 148/148 PASS  (22.13s)
Gate DO-178C (hook pre-commit) :       124/124 PASS
```

**Total R452 : 505 PASS — zéro régression introduite.**

Les 8 échecs `test_r406_versioning_robustness.py` sont **préexistants** (confirmés sur HEAD `9d2ca3f` avant R452 : identiques 8/8).

---

## Fingerprint artefact (L-053)

```json
{
  "r_task": "R452",
  "git_sha": "99c9259...",
  "modules": [
    "src/artcb/security/wallet_device_binding.py  v=1.3.4",
    "src/api/biometric_identity_routes.py          v=1.0.7",
    "tests/test_r452_forensic_coverage_api_binding.py",
    "src/artcb/trace/forensic.py                   v=1.0.1",
    "src/artcb/identity/biometric_onchain.py       v=1.0.4"
  ]
}
```

Artefact : `logs/R452_module_fingerprints.json` — `git_sha == HEAD` ✅ (L-053 respectée)

---

## Limites honnêtes

1. **`biometric_identity_routes.py` — test C04 stratégie structurelle** : le chemin nominal `enroll()` est couvert via mocks complets (pas d'appel HTTP réel). Les chemins d'erreur (unicité, sybil) sont implicitement couverts par les modules sous-jacents déjà testés.

2. **`emit_forensic()` = fail-open** : une panne I/O sur le ledger ne bloque jamais l'opération métier. C'est un choix délibéré (Critical Evidence Policy non encore définie — chantier FORENSIC-02).

3. **Critical Evidence Policy non implémentée** : la décision FAIL-CLOSED vs FAIL-OPEN par type d'événement est documentée comme future (FORENSIC-02). Aujourd'hui : tout forensic = FAIL-OPEN.

4. **Chiffrement at rest du ledger** : `forensic_ledger.jsonl` est en clair. Prévu FORENSIC-03.

---

## Chantiers suivants (inchangés de R430)

| Priorité | Chantier |
|---|---|
| P0 | **R432** — FHE Concrete `check_uniqueness()` |
| P1 | **FORENSIC-02** — Critical Evidence Policy (FAIL-CLOSED) |
| P1 | **CI GitHub** gate DO-178C obligatoire |
| P1 | **R433** — `reasoning.py` G4 |
| P1 | Chiffrement at rest `forensic_ledger.jsonl` |

---

*CERTIFIED_100=false — mode DEBUG actif*
