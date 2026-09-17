# R373 — Suppression UI biométrique de `/register` (R357)

**Date :** 2026-09-17  
**Commit source :** à pousser (suite de cda4495)  
**Auteur :** bob-ide  
**CERTIFIED_100 :** false (inchangé)

---

## 1. Contexte et motivation

L'audit de `main` (commit `cda4495`) a confirmé que la page `/register` exposait encore :

- Trois boutons de choix biométrique : **Empreinte**, **Visage**, **Empreinte + visage**
- Un composant caméra `<FaceCapture>` actif dans le parcours d'inscription
- Des appels directs à `faceEnrollOptions`, `faceEnrollVerify`, `faceLogin`, `faceLoginOptions`
- Le message "WebAuthn indisponible — la caméra faciale reste proposée"

Ce design violait la séparation architecturale fondamentale :

```
WebAuthn credential de l'OS
        ≠
choix biométrique affiché par ARTCB
        ≠
preuve d'identité humaine unique
        ≠
wallet ARTCB
```

---

## 2. Changements appliqués

### `frontend/src/pages/RegisterBiometric.tsx`
- **Supprimé :** imports `faceEnrollOptions`, `faceEnrollVerify`, `faceLogin`, `faceLoginOptions`, `webauthnStatus`
- **Supprimé :** import `FaceCapture`, `loadFaceSecret`, `saveFaceSecret`
- **Supprimé :** état `cameraOn`, `cameraIntent`, type `Modality`
- **Supprimé :** fonctions `enrollFaceCamera`, `loginFaceCamera`, `onLive`
- **Supprimé :** les 3 boutons Fingerprint / Face / Both
- **Supprimé :** `<FaceCapture active={cameraOn} ...>`
- **Ajouté :** un seul bouton **"Créer le wallet"** → WebAuthn natif de l'OS
- **Ajouté :** un seul bouton **"Se connecter"** en mode login
- **Principe :** ARTCB demande "authentifie cette opération" — l'OS décide du mécanisme (PIN/Touch ID/Face ID)

### `frontend/src/i18n/translations.ts`
- Ajout des clés `reg_*` (FR + EN) pour la nouvelle page
- Mise à jour `nav_register` FR : "S'inscrire" → "Créer wallet"
- Mise à jour `home_bio_cta` / `home_bio_cta_btn` : suppression de la référence à la biométrie

### `frontend/src/layout/DashboardLayout.tsx`
- Mise à jour du `title` du lien header : "Inscription biométrie" → "Créer un wallet"

---

## 3. Ce qui N'a PAS été supprimé

| Élément | Décision | Raison |
|---------|----------|--------|
| `FaceCapture` composant | **Conservé** (non utilisé dans `/register`) | D'autres pages ou tests pourraient l'utiliser |
| APIs backend face enrollment | **Conservées** | Auditées séparément — supprimer l'UI ne signifie pas supprimer le backend |
| `BiometricIdentityTest` page | **Conservée** | Page de test séparée (`/identity-test`) |
| `webauthnStatus` dans `client.ts` | **Conservée** | Utilisée potentiellement ailleurs |
| Clés i18n `bio_*` | **Conservées** | D'autres pages les utilisent (`Wallets`, etc.) |

---

## 4. Architecture résultante de `/register`

```
Utilisateur
    │
    ▼
Champ : Nom du wallet
    │
    ▼
Bouton : "Créer le wallet"
    │
    ▼
navigator.credentials.create() → WebAuthn
    │
    ▼
Authentificateur de l'OS (PIN / Touch ID / Face ID — géré par l'appareil)
    │
    ▼
Credential WebAuthn → Backend ARTCB
    │
    ▼
Wallet créé
```

**L'OS décide du mécanisme de déverrouillage. ARTCB ne le présente pas comme une fonctionnalité.**

---

## 5. Build

```
tsc -b && vite build
✓ 127 modules transformés
✓ dist/assets/index-CYz-Dq_b.js  260.84 kB
✓ build en 13.47s — 0 erreur TypeScript
```

---

## 6. Tests backend

```
PYTHONPATH=src python3 -m pytest tests/test_reasoning_record.py tests/test_reasoning_pbft.py
91/91 PASS
```

---

## 7. Ce qui reste à faire (chantiers parallèles)

- **PBFT primary mort** (`aws-node-3` offline) → publication on-chain bloquée
- **R357 enforcement** : vérifier que `BiometricIdentityTest` n'introduit pas les mêmes patterns dans d'autres pages visibles
- **Backend `face_camera`** : audit séparé des routes `/api/v1/identity/face/*` — conserver ou déprécier
- **`/identity-test`** : page à auditer (accessible depuis la nav, affiche "Test Biométrie")

---

## 8. Séparation garantie

| Couche | Statut |
|--------|--------|
| Présence faciale caméra dans `/register` | ❌ Supprimée |
| Choix Empreinte / Visage / Les deux | ❌ Supprimés |
| `FaceCapture` dans `/register` | ❌ Supprimé |
| WebAuthn comme mécanisme cryptographique | ✅ Conservé |
| Biométrie native OS (gérée par l'appareil) | ✅ Transparente (non présentée) |
| `CERTIFIED_100` | `false` — inchangé |

**ARTCB ne prétend plus que le choix "Visage" ou "Empreinte" est une preuve d'identité unique.**
