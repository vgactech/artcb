a# R384 — Correction Bug C : collision route `/webauthn/login/options`

**Date :** 2026-09-18  
**Commit :** à venir (ce rapport)  
**Tâche :** R384 — Bug WebAuthn `undefined.challenge` (Bug C — route dupliquée)  
**Statut :** ✅ PASS — 148/148 tests PASS | CERTIFIED_100=false

---

## Contexte

La session précédente avait identifié 3 bugs WebAuthn :

| Bug | Description | Statut avant R384 |
|-----|-------------|-------------------|
| A | `hints: ["client-device"]` bloquait le cross-device | ✅ corrigé R384-A |
| B | `getPlatformCredential()` sans validation → `undefined.challenge` | ✅ corrigé R384-B |
| C | Route `/webauthn/login/options` dupliquée → FastAPI écrasait `auth_router` par `webauthn_router` | ❌ **non corrigé** |

Ce rapport documente la correction du **Bug C**, cause racine du `undefined.challenge` en production.

---

## Diagnostic — Cause racine

### Deux routers, même prefix, même chemin

```
auth_routes.py      : prefix="/api/v1/auth"  + route "/webauthn/login/options"
webauthn_routes.py  : prefix="/api/v1/auth"  + route "/webauthn/login/options"
```

URL finale identique dans les deux cas : `/api/v1/auth/webauthn/login/options`

### Ordre de montage dans `src/api/main.py`

```python
app.include_router(auth_router)      # ligne 403
app.include_router(webauthn_router)  # ligne 404
```

**Comportement FastAPI :** le dernier router enregistré pour une URL donnée **gagne**. `webauthn_router` (ligne 404) écrasait silencieusement `auth_router` (ligne 403).

### Formats de réponse incompatibles

| Route | Format retourné | Attendu par |
|-------|----------------|-------------|
| `auth_routes.py` (flux ARTCB template_hex) | `{"challenge": "...", "hint": "...", "certified_100": false, ...}` | `test_webauthn_artcb_login.py` |
| `webauthn_routes.py` (flux FIDO2 standard) | `{"publicKey": {...challenge...}, "raw_biometric_never_stored": true}` | `test_webauthn_biometric.py` + frontend |

### Impact concret

- `test_webauthn_artcb_login.py` : `assert "challenge" in data` → **KeyError** car la route reçue retournait `publicKey` sans `challenge` nu
- `test_webauthn_biometric.py::test_fingerprint_register_and_login` : `login_opt.json()["publicKey"]` → **KeyError** car la route reçue pouvait varier selon l'ordre d'enregistrement
- Frontend : `undefined.challenge` — la réponse reçue ne correspondait pas au format attendu par `getPlatformCredential()`

---

## Correction appliquée

### AVANT (`src/api/auth_routes.py`)

```python
# ligne 571-572
@router.post(
    "/webauthn/login/options",          # ← collision avec webauthn_routes.py
    ...
)
def webauthn_login_options(...):
    ...

# ligne 601-602
@router.post(
    "/webauthn/login/verify",           # ← collision potentielle
    ...
)
def webauthn_login_verify(...):
    ...
```

### APRÈS (`src/api/auth_routes.py`)

```python
# ligne 576
@router.post(
    "/webauthn/biometric/options",      # ← URL distincte, plus de collision
    ...
)
def webauthn_biometric_options(...):
    ...

# ligne 607
@router.post(
    "/webauthn/biometric/verify",       # ← URL distincte, plus de collision
    ...
)
def webauthn_biometric_verify(...):
    ...
```

URLs finales après renommage :
- `POST /api/v1/auth/webauthn/biometric/options` → flux ARTCB template_hex (challenge bare)
- `POST /api/v1/auth/webauthn/biometric/verify` → vérification template biométrique ARTCB
- `POST /api/v1/auth/webauthn/login/options` → flux FIDO2 standard (inchangé, `webauthn_routes.py`)
- `POST /api/v1/auth/webauthn/login/verify` → flux FIDO2 standard (inchangé, `webauthn_routes.py`)

### Tests mis à jour (`tests/test_webauthn_artcb_login.py`)

14 occurrences `/api/v1/auth/webauthn/login/options` → `/api/v1/auth/webauthn/biometric/options`  
14 occurrences `/api/v1/auth/webauthn/login/verify` → `/api/v1/auth/webauthn/biometric/verify`  
Docstring + commentaires de section mis à jour avec la mention R384.

---

## Résultats des tests

```
tests/test_webauthn_artcb_login.py   19/19 PASS  ← était partiellement FAIL
tests/test_webauthn_biometric.py      5/5  PASS  ← test_fingerprint_register_and_login PASS
tests/test_task001_biometric.py      18/18 PASS  ← non-régression
tests/test_task001_r374_bch.py       30/30 PASS  ← non-régression
tests/test_task001_r376_uniqueness.py 22/22 PASS ← non-régression
tests/test_task001_r378_hamming.py   28/28 PASS  ← non-régression
tests/test_task001_r373_human_identity_policy.py 26/26 PASS ← non-régression
─────────────────────────────────────────────────
TOTAL                                148/148 PASS ✅
```

---

## Architecture des deux flux WebAuthn (après R384)

```
Client navigateur
       │
       ├── Flux FIDO2 standard (credential navigator)
       │     POST /api/v1/auth/webauthn/login/options   → {"publicKey": {...}}
       │     POST /api/v1/auth/webauthn/login/verify    → session FIDO2
       │     Source : webauthn_routes.py
       │
       └── Flux ARTCB template biométrique
             POST /api/v1/auth/webauthn/biometric/options → {"challenge": "...", "hint": "..."}
             POST /api/v1/auth/webauthn/biometric/verify  → session ARTCB biométrique
             Source : auth_routes.py
```

Les deux flux coexistent sans collision. `webauthn_routes.py` reste le flux recommandé pour les navigateurs avec WebAuthn natif. `auth_routes.py` (flux biométrique ARTCB) est le flux pour les clients qui transmettent un `template_hex` normalisé directement.

---

## Invariants maintenus

- `unique_human_proven = False` dans tous les chemins ✅
- `CERTIFIED_100 = False` ✅
- Aucune image brute acceptée (PNG/JPEG/BMP magic bytes rejetés) ✅
- Challenge usage unique (TTL + suppression post-vérification) ✅
- OVH1 non contacté ✅

---

## Fichiers modifiés

| Fichier | Modification |
|---------|-------------|
| `src/api/auth_routes.py` | Routes renommées `/login/` → `/biometric/`, fonctions renommées, commentaire R384 |
| `tests/test_webauthn_artcb_login.py` | 28 URLs mises à jour, docstring R384 |

**Fichiers non modifiés :** `src/api/webauthn_routes.py`, `frontend/src/api/client.ts`, `src/api/main.py`

---

## Limites honnêtes

- Le flux `/webauthn/biometric/verify` utilise encore le matching hash exact (stub). Production : FHE/TEE (TASK-001).
- `unique_human_proven = False` — le hash exact n'est pas une preuve biométrique certifiée.
- Les clients qui appelaient `/auth/webauthn/login/options` sans `name` (flux ARTCB) doivent migrer vers `/auth/webauthn/biometric/options`.

`CERTIFIED_100=false`
