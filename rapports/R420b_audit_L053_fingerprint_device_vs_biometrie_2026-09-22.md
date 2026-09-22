# R420b — Audit L-053 : fingerprint device vs preuve biométrique — état réel HEAD 7b46eba

**Date :** 2026-09-22  
**SHA audité :** `7b46eba` (HEAD après R420-fp)  
**Commit R420 :** `01e3aa0`  
**Push confirmé :** `7a6c04f..7b46eba main -> main` ✅  
**CERTIFIED_100 :** false  
**Mode DEBUG actif**

---

## 1. Clarification — deux "fingerprint" distincts dans ARTCB

L'audit externe confond deux concepts différents qui portent le même mot :

| Concept | Fichier source | Rôle |
|---------|---------------|------|
| **`logs/R394_module_fingerprints.json`** | `scripts/artcb_r390_add_module_version.py` | SHA-256 de chaque module Python — traçabilité du code source (L-053) |
| **`device_fingerprint`** | `src/api/auth_routes.py:68` | Empreinte appareil client (User-Agent + X-ARTCB-Device-Id) — anti-fraude 1 wallet/device |

L-053 porte sur le **premier** (fingerprint code source). L'audit externe porte sur le **second** (fingerprint device). Les deux sont distincts et légitimes. Ce rapport couvre les deux.

---

## 2. L-053 — Fingerprint code source : état vérifié sur HEAD 7b46eba

### Séquence L-053 respectée sur R420

```
R420 développement
      ↓
98 tests PASS (biometric, bch, uniqueness, hamming)
      ↓
git commit 01e3aa0 (R420)
      ↓
python3 scripts/artcb_r390_add_module_version.py --fingerprint-only
      ↓
logs/R394_module_fingerprints.json → git_sha=01e3aa0 (295 modules)
      ↓
git commit 7b46eba (R420-fp)
      ↓
git push 7a6c04f..7b46eba ✅
```

**Vérification :**
- `logs/R394_module_fingerprints.json` : `git_sha = "01e3aa0"` ✅
- HEAD actuel : `7b46eba` (commit fingerprint séparé) ✅
- Convention L-053 : artefact porte le SHA du commit de travail, pas du commit fingerprint lui-même ✅

---

## 3. Fingerprint device — Audit architectural complet

### 3.1 Construction du fingerprint (`src/api/auth_routes.py:68`)

```python
def device_fingerprint(request: Request | None) -> str:
    ua  = request.headers.get("user-agent") or ""
    dev = request.headers.get("x-artcb-device-id") or ""
    return hashlib.sha256(f"{ua}|{dev}".encode()).hexdigest()[:32]
```

**Ce que c'est :** hash SHA-256[:32] du couple `(User-Agent, X-ARTCB-Device-Id)`.  
**Ce que ce n'est pas :** preuve biométrique, attestation TPM, identité humaine.

### 3.2 Réponse aux questions de l'audit externe

| Question audit | Réponse sur HEAD 7b46eba | Preuve |
|---------------|--------------------------|--------|
| Fingerprint = identifiant d'appareil connu ? | ✅ OUI — "Cet appareil est-il déjà enregistré ?" | `wallet_device_bindings.json` — clé `device_fingerprint` |
| Fingerprint = preuve biométrique ? | ✅ INTERDIT — `unique_human_proven=False` dans tous les chemins | `webauthn_routes.py` lignes 231, 253, 302, 511, 519, 559 |
| Détection changement d'appareil | ✅ OUI — HTTP 409 `device_wallet_limit` si fingerprint différent sur même wallet | `wallet_device_binding.py:165-177` |
| Liaison humain↔credential WebAuthn↔appareil | ✅ PRÉSENTE — WebAuthn `credential_id` lié au wallet; `device_fingerprint` lié au wallet; les deux sont distincts | `webauthn_routes.py:190,212,217` |
| Résistance réinstallation/changement navigateur | ⚠️ PARTIELLE — User-Agent seul peut changer; `X-ARTCB-Device-Id` est le vrai discriminant — si le client ne génère pas ce header, le fingerprint est moins stable | `auth_routes.py:77-81` |
| Combiné avec WebAuthn non-exportable | ✅ OUI — credential WebAuthn stocké côté serveur (`credential_id` + clé COSE); le fingerprint device est une couche supplémentaire, pas un substitut | `webauthn_routes.py:338-367` |
| `unique_human_proven` reste False avec fingerprint | ✅ GARANTI — invariant dans tous les chemins | 6 occurrences vérifiées |

### 3.3 Limites honnêtes documentées

1. **`X-ARTCB-Device-Id` côté client** : si le navigateur/app ne génère pas cet en-tête, le fingerprint se réduit au User-Agent seul, moins discriminant.
2. **Fingerprint logiciel ≠ attestation matérielle** : pas de TPM/Secure Enclave live (DV-01 note : "attestation requise plus tard pour production critique").
3. **Changement de navigateur** : possible de contourner le binding device en changeant navigateur + User-Agent. La vraie protection anti-Sybil reste la couche WebAuthn + `check_wallet_per_human_limit()` (R373).
4. **Reset admin disponible** : `DELETE /api/v1/admin/device-binding/fingerprint/{fingerprint}` (R379) — réservé opérateur.

### 3.4 Architecture correcte confirmée

```
HUMAIN
  │
  │ vérification biométrique OS (Touch ID / Face ID)
  ▼
WebAuthn Credential (credential_id + clé COSE) — non exportable
  │
  │ possession
  ▼
APPAREIL (device_fingerprint = sha256(User-Agent|X-ARTCB-Device-Id))
  │
  │ binding 1:1
  ▼
WALLET (wallet_device_bindings.json)
```

`unique_human_proven=False` dans tous les chemins — conforme à L-047/R372.

---

## 4. Vérifiabilité du commit 01e3aa0

L'audit externe signale que `01e3aa0` n'est pas résolvable sur GitHub au moment de l'audit.

**Explication :** le push a été effectué dans la session R420-fp (`7b46eba`) **après** la question posée par l'expert. L'ordre chronologique était :

```
commit 01e3aa0 (local, non pushé au moment de la question)
      ↓
question expert reçue
      ↓
fingerprint généré → commit 7b46eba
      ↓
git push 7a6c04f..7b46eba ← push effectif
```

Donc au moment de la question, `01e3aa0` existait localement mais n'était pas encore sur `origin/main`. C'est conforme à L-049 (working tree ≠ pushé). L'expert a eu raison de signaler l'absence sur GitHub.

**État actuel :** `origin/main = 7b46eba` — les deux commits (`01e3aa0` + `7b46eba`) sont sur GitHub.

---

## 5. Résumé — AVANT / APRÈS R420 complet

| Élément | AVANT (7a6c04f) | APRÈS (7b46eba) |
|---------|----------------|----------------|
| `public_lock().distributed_certified` | `False` codé en dur | Dynamique = `certification_gate()` → `True` |
| RESULT.json DV-01..07 | Sans provenance | `git_sha + protocol_version + genesis_hash` |
| Ledger `git_head` | `23f9613` (obsolète) | `7a6c04f` (HEAD R419 correct) |
| Frontend route `/identity-test` | Active | Supprimée (R420) |
| Fingerprint `logs/R394_module_fingerprints.json` | `git_sha=fc9df76` (convention R417) | `git_sha=01e3aa0` (HEAD commit R420) |
| `unique_human_proven` | `False` dans tous les chemins | `False` dans tous les chemins (invariant maintenu) |

---

## 6. Chantiers ouverts confirmés (L-055 appliquée — vérifiés sur HEAD)

| Priorité | Chantier |
|----------|----------|
| P0 | FHE véritable `check_uniqueness()` — SEAL/OpenFHE/Concrete |
| P0 | FAR/FRR/PAD sur vrais capteurs biométriques |
| P1 | `X-ARTCB-Device-Id` — documenter/enforcer la génération côté client |
| P1 | DV-05 rejouer PBFT append_block complet |
| P1 | DV-06 chaos C complet |
| P2 | Attestation TPM/Secure Enclave (DV-01 note) |

---

*Rapport R420b — mode DEBUG ARTCB — jamais écraser les anciens rapports.*
