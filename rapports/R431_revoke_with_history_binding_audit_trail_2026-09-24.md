# R431 — Révocation de binding wallet↔device avec historique conservé

**Date :** 2026-09-24  
**SHA HEAD avant commit :** `2da58078d2f07869c06dfd5f135594123fa9b8eb`  
**Auteur :** Bob IDE (agent)  
**Avancement global :** ~53 %  
**CERTIFIED_100 :** false  

---

## Contexte

Le rapport R430 a identifié que les méthodes `admin_revoke_*` (R379) effectuaient une **suppression physique** (DELETE) de l'enregistrement dans le registre JSON. Ce comportement est incompatible avec un audit trail fiable : si le binding est supprimé, il est impossible de vérifier ultérieurement qu'un appareil a bien été révoqué, par qui, pour quelle raison et à quel moment.

R431 introduit un modèle d'état explicite :

```
Binding
  ├── ACTIVE   (état initial à la création)
  └── REVOKED  (après révocation — enregistrement conservé)
```

La révocation physique (DELETE) des endpoints R379 est **dépréciée mais conservée** pour la rétro-compatibilité.

---

## Fichiers modifiés

### 1. `src/artcb/security/wallet_device_binding.py`

| Élément | Avant R431 | Après R431 |
|---------|-----------|------------|
| `MODULE_VERSION` | `'1.0.0'` | `'1.1.0'` |
| Import `uuid` | absent | ajouté |
| Classe `BindingState` | absente | `ACTIVE = "ACTIVE"`, `REVOKED = "REVOKED"` |
| Classe `BindingRevocationError` | absente | levée en cas de révocation invalide |
| `check_and_bind` — filtre sur `existing` | tous les enregistrements bloquent | seuls les ACTIVE bloquent (REVOKED ignorés) |
| Champs enregistrement PRODUCTION | `wallet_name, device_fingerprint, env_type, namespace, created_at` | + `binding_id (uuid4), state, revoked_at, revocation_reason, revocation_actor` |
| Champs enregistrement TEST | idem PRODUCTION | idem |
| `revoke_with_history()` | absente | révoque ACTIVE→REVOKED, conserve l'historique |
| `get_binding_by_id()` | absente | récupère par `binding_id` (ACTIVE ou REVOKED) |
| `list_active_bindings()` | absente | filtre les ACTIVE uniquement |
| `list_revoked_bindings()` | absente | filtre les REVOKED uniquement |

#### Extrait avant (ligne 195, `check_and_bind`) :
```python
records.append({
    "wallet_name": wallet_name,
    "device_fingerprint": device_fingerprint,
    "env_type": env_type,
    "namespace": "PRODUCTION",
    "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
})
```

#### Extrait après :
```python
records.append({
    "binding_id": str(uuid.uuid4()),
    "wallet_name": wallet_name,
    "device_fingerprint": device_fingerprint,
    "env_type": env_type,
    "namespace": "PRODUCTION",
    "state": BindingState.ACTIVE,
    "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "revoked_at": None,
    "revocation_reason": None,
    "revocation_actor": None,
})
```

#### Migration transparente (lecture seule)
Les anciens enregistrements sans champ `state` sont traités comme `ACTIVE` via `.get("state", BindingState.ACTIVE)`. Aucune migration en écriture n'est effectuée sur les fichiers existants.

---

### 2. `src/api/admin_device_binding_routes.py`

| Élément | Avant R431 | Après R431 |
|---------|-----------|------------|
| `MODULE_VERSION` | `'1.0.0'` | `'1.1.0'` |
| Import `Body` | absent | `from fastapi import ..., Body, ...` |
| Import `BindingRevocationError` | absent | `from src.artcb.security.wallet_device_binding import BindingRevocationError` |
| `GET /list-active` | absent | liste les ACTIVE uniquement |
| `GET /list-revoked` | absent | liste les REVOKED (audit trail) |
| `POST /revoke` | absent | révoque avec historique (R431) |
| `DELETE /fingerprint/{fp}` | actif | conservé, marqué DEPRECATED |
| `DELETE /wallet/{name}` | actif | conservé, marqué DEPRECATED |
| `DELETE /test/wallet/{name}` | actif | conservé, marqué DEPRECATED |

---

### 3. `tests/test_r431_revoke_with_history.py` (NOUVEAU)

9 cas T01→T09 :

| Test | Description | Résultat |
|------|-------------|----------|
| T01 | Binding actif peut être révoqué | ✅ PASS |
| T02 | État = REVOKED après révocation | ✅ PASS |
| T03 | Enregistrement conservé (non supprimé) | ✅ PASS |
| T04 | Binding REVOKED n'empêche plus la création d'un nouveau wallet | ✅ PASS |
| T05 | Sans critère → BindingRevocationError | ✅ PASS |
| T06 | Double révocation → BindingRevocationError (409) | ✅ PASS |
| T07 | Audit trail : binding_id, wallet_name, device_fingerprint, created_at conservés | ✅ PASS |
| T08 | Révocation par binding_id (prioritaire) | ✅ PASS |
| T09 | Non-régression : DELETE physiques R379 fonctionnent toujours | ✅ PASS |

---

## Résultats des tests

```
tests/test_r431_revoke_with_history.py .........  9/9 PASS (0.79s)
tests/test_r345_wallet_client_binding.py ..       2/2 PASS (non-régression)
─────────────────────────────────────────────────
Total : 11/11 PASS
```

**Régression préexistante hors périmètre R431 :**  
`tests/test_add_device_r363.py::TestAddDeviceValid::test_max_5_devices_enforced` — échec confirmé sur HEAD `2da5807` AVANT R431 (vérifié par git stash + re-test). Ce test n'est pas lié à R431.

---

## Invariants vérifiés

- `unique_human_proven` : non concerné par ce chantier (couche device ≠ couche human)
- `CERTIFIED_100` : reste `false`
- Les bindings REVOKED ne bloquent pas la création d'un nouveau wallet pour le même device (T04)
- L'audit trail est immuable une fois REVOKED (double révocation bloquée, T06)
- Les enregistrements antérieurs sans `state` sont lus comme ACTIVE (migration transparente)

---

## Modèle d'état complet

```
check_and_bind()
     │
     ▼
 { binding_id: uuid4,
   state: "ACTIVE",
   wallet_name: ...,
   device_fingerprint: ...,
   created_at: ...,
   revoked_at: null,
   revocation_reason: null,
   revocation_actor: null }
     │
     │  POST /api/v1/admin/device-binding/revoke
     ▼
 { ...mêmes champs...,
   state: "REVOKED",
   revoked_at: "2026-...",
   revocation_reason: "...",
   revocation_actor: "admin" }
     │
     │  Enregistrement CONSERVÉ dans le registre JSON
     ▼
 list_revoked_bindings() → audit trail visible
```

---

## Prochaines étapes (non traitées dans R431)

- **R432** — FHE Concrete pour `check_uniqueness()` (TASK-001-BIOMETRIE-SUITE)
- **R433** — `reasoning.py` G4 (ARTCD)
- `test_add_device_r363.py::test_max_5_devices_enforced` — régression préexistante à investiguer séparément

---

**CERTIFIED_100 = false**
