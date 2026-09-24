# R454 — Gate WebAuthn FAIL-CLOSED : PIN seul / face_camera → rejet (Issue #89)

**Date :** 2026-09-25  
**SHA commit :** `6811ed90a14c4e10df45edbf0b0174c7c7a79cb7`  
**SHA parent :** `8c4822b` (R453-rapport)  
**Auteur :** agent ARTCB (Bob IDE)  
**Statut :** ✅ DONE — 25/25 tests PASS — Gate DO-178C 124/124 PASS  
**CERTIFIED_100 :** `false`

---

## 1. Contexte — Issue #89

L'audit R430 et les rapports experts identifiaient une limite critique :

> *Le serveur ne doit pas essayer de déterminer lui-même qu'une image ressemble à une empreinte ou à un visage. Il doit vérifier une **preuve cryptographique** provenant du mécanisme d'authentification prévu.*

Le code existant avait `face_camera` documenté comme FALLBACK ACCESSIBILITÉ (`ASSURANCE_LEVELS["face_camera"].level = 1`) mais **aucun mécanisme FAIL-CLOSED** n'empêchait `face_camera` ou `PIN` d'atteindre les opérations critiques (création wallet, économique).

Invariant fondamental rappelé :

```
PIN seul    ≠   preuve biométrique
face_camera ≠   authenticateur natif WebAuthn
```

---

## 2. Fichiers créés

| Fichier | Action | Rôle |
|---------|--------|------|
| `src/artcb/security/webauthn_failclosed.py` | **NOUVEAU** | Module gate FAIL-CLOSED |
| `tests/test_r454_webauthn_failclosed.py` | **NOUVEAU** | 25 tests W01–W25 |

### Avant (absence de gate)

Aucun module n'implémentait de politique de rejet explicite par modalité d'authentification pour les opérations critiques.  
`face_camera` pouvait théoriquement atteindre n'importe quelle opération si l'appelant ne vérifiait pas `ASSURANCE_LEVELS`.

### Après — `webauthn_failclosed.py`

Architecture à 3 couches :

```
AuthModality   (modalité présentée)
     ↓
WebAuthnContext  (contexte complet : UV, platform, assertion, etc.)
     ↓
evaluate_gate(ctx, operation)
     ↓
WebAuthnGateResult.allowed : True / False (FAIL-CLOSED)
```

**Hiérarchie des opérations :**

| Opération | face_camera | PIN/UNKNOWN | WebAuthn platform BIOMETRIC |
|-----------|------------|------------|---------------------------|
| `LOGIN` | ✅ autorisé | ✅ autorisé | ✅ autorisé |
| `WALLET_CREATE` | ❌ refusé | ❌ refusé | ✅ autorisé |
| `ECONOMIC` | ❌ refusé | ❌ refusé | ✅ autorisé |
| `ENROLL_DEVICE` | ❌ refusé | ❌ refusé | ✅ autorisé |
| `ADMIN` | ❌ refusé | ❌ refusé | ✅ autorisé |

---

## 3. Couverture des 25 tests

| Test | Scénario | Résultat |
|------|----------|----------|
| W01 | PIN + WALLET_CREATE → `pin_not_sufficient` | ✅ PASS |
| W02 | UNKNOWN uv_method + WALLET_CREATE → refusé | ✅ PASS |
| W03 | face_camera + WALLET_CREATE → `face_camera_not_sufficient` | ✅ PASS |
| W04 | face_camera + ECONOMIC → refusé | ✅ PASS |
| W05 | face_camera + ENROLL_DEVICE → refusé | ✅ PASS |
| W06 | face_camera + ADMIN → refusé | ✅ PASS |
| W07 | PIN + ECONOMIC → `pin_not_sufficient` | ✅ PASS |
| W08 | UNKNOWN modality + WALLET_CREATE → FAIL-CLOSED | ✅ PASS |
| W09 | roaming sans platform_bound → `platform_authenticator_required` | ✅ PASS |
| W10 | assertion_valid=False → `assertion_not_valid` | ✅ PASS |
| W11 | user_verified=False + ECONOMIC → `user_verification_required` | ✅ PASS |
| W12 | WebAuthn platform + BIOMETRIC + WALLET_CREATE → autorisé | ✅ PASS |
| W13 | WebAuthn platform + BIOMETRIC + ECONOMIC → autorisé | ✅ PASS |
| W14 | WebAuthn platform + BIOMETRIC + ENROLL_DEVICE → autorisé | ✅ PASS |
| W15 | WebAuthn platform + BIOMETRIC + ADMIN → autorisé | ✅ PASS |
| W16 | face_camera + LOGIN → autorisé (tolérant) | ✅ PASS |
| W17 | PIN + LOGIN → autorisé (tolérant) | ✅ PASS |
| W18 | UNKNOWN modality + LOGIN → autorisé (tolérant) | ✅ PASS |
| W19 | unique_human_proven=False dans TOUS les cas | ✅ PASS |
| W20 | WebAuthnContext.unique_human_proven invariant (forçage à True ignoré) | ✅ PASS |
| W21 | WebAuthnGateResult.unique_human_proven invariant | ✅ PASS |
| W22 | from_session() → UNKNOWN si modalité non reconnue | ✅ PASS |
| W23 | from_session() → FACE_CAMERA correctement mappé | ✅ PASS |
| W24 | from_session() → webauthn_fingerprint → WEBAUTHN_PLATFORM | ✅ PASS |
| W25 | Helpers haut niveau cohérents (wallet / economic / device / login) | ✅ PASS |

---

## 4. Invariants inviolables implémentés

1. `face_camera` n'autorise **jamais** `WALLET_CREATE` — code machine : `face_camera_not_sufficient`
2. `PIN` / `UNKNOWN` n'autorisent **jamais** `ECONOMIC` — code machine : `pin_not_sufficient`
3. `cross-platform` sans `is_platform_bound=True` refusé pour `WALLET_CREATE` / `ADMIN` — `platform_authenticator_required`
4. `unique_human_proven` est **toujours `False`** dans `WebAuthnContext` et `WebAuthnGateResult` — `__post_init__` l'écrase même si forcé à `True`
5. FAIL-CLOSED : modalité UNKNOWN pour opération stricte → refus systématique

---

## 5. Non-régression

| Suite | Tests | Résultat |
|-------|-------|----------|
| R454 (nouveau) | 25 | ✅ PASS |
| R453 PBFT view-change | 25 | ✅ PASS |
| R452 Forensic coverage | 16 | ✅ PASS |
| R451 ForensicEvent | 30 | ✅ PASS |
| Gate DO-178C pre-commit | 124 | ✅ PASS |

---

## 6. Fingerprint modules

| Module | SHA-256 (16 premiers octets) |
|--------|------------------------------|
| `src/artcb/security/webauthn_failclosed.py` | `0fda40e36f4090f1...` |
| `tests/test_r454_webauthn_failclosed.py` | `5540dce9957ce9b5...` |
| `src/artcb/identity/human_identity_policy.py` | `9568a4a0ec8604cb...` |
| `src/api/webauthn_routes.py` | `17d9fc64325a3866...` |

Artefact : `logs/R454_module_fingerprints.json` (git_sha = `6811ed9`)

---

## 7. Limites honnêtes

1. **Ce module n'est pas encore branché** sur `webauthn_routes.py` — il doit être appelé explicitement avant chaque opération critique. L'intégration sur l'API est le chantier suivant (R455 ou point d'entrée dédié).
2. **`from_session()` est conservateur** : une session avec `modality="webauthn_fingerprint"` + `is_platform_bound=False` est quand même rejetée pour `WALLET_CREATE` (vérification V09 cross-platform).
3. **BIOMETRIC ≠ unique_human_proven** : même `UserVerificationMethod.BIOMETRIC` ne passe pas `unique_human_proven=True` — le gate n'inverse pas cet invariant fondamental.
4. **`UserVerificationMethod.BIOMETRIC` = auto-déclaré** (côté client) — le serveur ne peut pas l'attester cryptographiquement sans mécanisme d'attestation supplémentaire.

---

## 8. Prochaines étapes

| Priorité | Chantier |
|----------|----------|
| P0 | **R455** — Issue #90 : Bypass internes (capability à usage unique) |
| P0 | **R456** — Issue #77 : NodeID ↔ clé TPM/live — 9 scénarios adversariaux |
| P0 | Intégrer R454 gate sur `webauthn_routes.py` (appel explicite avant opération critique) |
| P1 | CI GitHub gate DO-178C autorité finale |

**CERTIFIED_100 reste `false`.**
