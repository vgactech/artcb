# R455 — D-046 face_camera UNSUPPORTED : Gate FAIL-CLOSED toutes opérations + /face/* 410 Gone

**Date :** 2026-09-25  
**SHA commit :** `06db528`  
**SHA parent (R454) :** `f681103`  
**Fingerprint :** `logs/R455_module_fingerprints.json` (généré sur `06db528`)  
**CERTIFIED_100 :** `false`  
**Avancement global estimé :** 55 %

---

## 1. Contexte

R454 a implémenté le gate WebAuthn FAIL-CLOSED (25 tests W01-W25). La décision D-046 (2026-09-25) est venue interdire **toute utilisation de `face_camera`** dans ARTCB, y compris pour le LOGIN — opération qui était encore tolérée dans R454. R455 applique cette décision de manière absolue sur tous les chemins.

---

## 2. Périmètre R455

| Fichier modifié | Nature de la modification |
|-----------------|--------------------------|
| `src/artcb/security/webauthn_failclosed.py` | `MODULE_VERSION` → `1.1.0` ; `FACE_CAMERA_POLICY = "UNSUPPORTED_D046"` ; `evaluate_gate()` : rejet `face_camera_unsupported_d046` **en vérification 0** pour **toutes les opérations** ; `is_pin_equivalent()` retire `FACE_CAMERA` |
| `src/artcb/security/webauthn_store.py` | `MODULE_VERSION` → `1.1.0` ; `ALLOWED_MODALITIES = frozenset({"fingerprint"})` (MODALITY_FACE retiré) ; `FACE_CAMERA_UNSUPPORTED = True` sentinel |
| `src/api/webauthn_routes.py` | `FACE_CAMERA_INACTIVE_PRODUCTION = True` ; 4 endpoints `/face/enroll/options`, `/face/enroll/verify`, `/face/login`, `/face/login/options` → `HTTPException(410)` avec `detail["error"] = "face_camera_unsupported_d046"` |
| `tests/test_r454_webauthn_failclosed.py` | 3 tests mis à jour D-046 (W03 reason, W16 login désormais refusé, W25 assertion D-046) |
| `tests/test_r455_d046_face_camera_unsupported.py` | **NOUVEAU** — 20 tests F01-F20 |

---

## 3. Avant / Après

### `webauthn_failclosed.py` — `evaluate_gate()`

**AVANT (R454) :**
```python
# FACE_CAMERA autorisé pour LOGIN uniquement
if ctx.operation == "login":
    return GateResult(allowed=True, ...)
# face_camera rejeté pour wallet_create/economic/enroll_device/admin
```

**APRÈS (R455) :**
```python
FACE_CAMERA_POLICY = "UNSUPPORTED_D046"

def evaluate_gate(ctx: WebAuthnContext) -> GateResult:
    # Vérification 0 — D-046 : face_camera rejeté TOUTES opérations sans exception
    if ctx.modality == MODALITY_FACE_CAMERA:
        return GateResult(
            allowed=False,
            reason="face_camera_unsupported_d046",
            unique_human_proven=False,
        )
    # ... reste du gate inchangé
```

### `webauthn_store.py` — `ALLOWED_MODALITIES`

**AVANT (R454) :**
```python
ALLOWED_MODALITIES = frozenset({MODALITY_FINGERPRINT, MODALITY_FACE})
```

**APRÈS (R455) :**
```python
ALLOWED_MODALITIES = frozenset({MODALITY_FINGERPRINT})
FACE_CAMERA_UNSUPPORTED = True  # D-046 sentinel
```

### `webauthn_routes.py` — endpoints /face/*

**AVANT (R454) :**
```python
@router.post("/face/enroll/options")
async def face_enroll_options(...):
    # logique active
```

**APRÈS (R455) :**
```python
FACE_CAMERA_INACTIVE_PRODUCTION = True  # D-046

@router.post("/face/enroll/options")
async def face_enroll_options_disabled():
    raise HTTPException(status_code=410, detail={"error": "face_camera_unsupported_d046"})

# idem pour /face/enroll/verify, /face/login, /face/login/options
```

---

## 4. Résultats des tests

| Suite | Résultat |
|-------|----------|
| `test_r455_d046_face_camera_unsupported.py` (F01–F20) | **20/20 PASS** |
| `test_r454_webauthn_failclosed.py` (W01–W25) | **25/25 PASS** |
| Gate DO-178C (hook R430) | **124/124 PASS** |
| Non-régression R451/R452/R453/R432 | **102/102 PASS** |
| **Total session** | **147/147 PASS** |

### Détail des 20 tests F01-F20

| Test | Description | Résultat |
|------|-------------|---------|
| F01 | face_camera LOGIN → denied D-046 | PASS |
| F02 | face_camera wallet_create → denied | PASS |
| F03 | face_camera economic → denied | PASS |
| F04 | face_camera enroll_device → denied | PASS |
| F05 | face_camera admin → denied | PASS |
| F06 | reason cohérent toutes opérations = `face_camera_unsupported_d046` | PASS |
| F07 | MODALITY_FACE absent de ALLOWED_MODALITIES | PASS |
| F08 | FACE_CAMERA_UNSUPPORTED sentinel = True | PASS |
| F09 | ALLOWED_MODALITIES = {"fingerprint"} uniquement | PASS |
| F10 | GET /face/enroll/options → 410 | PASS |
| F11 | POST /face/enroll/verify → 410 | PASS |
| F12 | POST /face/login → 410 | PASS |
| F13 | POST /face/login/options → 410 | PASS |
| F14 | payload 410 contient `face_camera_unsupported_d046` | PASS |
| F15 | FACE_CAMERA_POLICY = "UNSUPPORTED_D046" | PASS |
| F16 | FACE_CAMERA_INACTIVE_PRODUCTION = True | PASS |
| F17 | platform biometric LOGIN encore autorisé | PASS |
| F18 | platform biometric wallet_create encore autorisé | PASS |
| F19 | unique_human_proven=False même platform biometric | PASS |
| F20 | from_session() face_camera → détecté et denied | PASS |

---

## 5. Invariants maintenus

- `unique_human_proven=False` dans **tous les chemins** (invariant global ARTCB)
- `CERTIFIED_100=false`
- `face_camera` rejeté avant toute autre logique (priorité absolue D-046)
- Biométrie platform (Touch ID, Face ID OS, Windows Hello) = **toujours autorisée** via WebAuthn natif FIDO
- ARTCB ne reçoit **jamais** d'image faciale directe

---

## 6. Fingerprint

```json
{
  "r_task": "R455",
  "git_sha": "06db528...",
  "modules": [
    {"path": "src/artcb/security/webauthn_failclosed.py", "module_version": "1.1.0"},
    {"path": "src/artcb/security/webauthn_store.py", "module_version": "1.1.0"},
    {"path": "src/api/webauthn_routes.py", "..."},
    {"path": "tests/test_r454_webauthn_failclosed.py", "..."},
    {"path": "tests/test_r455_d046_face_camera_unsupported.py", "..."}
  ]
}
```

---

## 7. Prochaines étapes

| R# | Issue | Description |
|----|-------|-------------|
| **R456** | #90 | Bypasses internes capability à usage unique |
| **R457** | #77 | NodeID ↔ clé TPM/live — 9 scénarios adversariaux |
| CI GitHub | R430 préconisation | Gate DO-178C autorité finale (hook local = seul niveau actuel) |
| TASK-001 | — | FAR/FRR/PAD biométrie vrais capteurs |
| R432-bis | — | FHE Concrete réel `check_uniqueness()` |

---

*Rapport généré post-exécution — ARTCB protocole R455 — SHA `06db528`*
