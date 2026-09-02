# Rapport 208 — État, biométrie, preuves DV, pourquoi ce n’est pas encore certified

**Horodatage :** 2026-09-02T21:20:00Z  
**Certification :** **NOT MAINNET CERTIFIED**  
**Raison mesurée du gate :** `dv_not_pass:DV-02,DV-06` (RESULT.json encore PARTIAL au départ de ce tour) **et** `operator_certification_go=false`

Rien n’est inventé. PEM / tokens non imprimés. PR **#51 rescue non fusionnée**.

## 1. État d’avancement (live au bootstrap de ce tour)

| Item | Mesure |
|------|--------|
| GitHub `origin/main` | `91dd6e91d2c04ae1a977a96f3f688d1bfc98f264` |
| Live OVH1 `/health` | HTTP 200, **même SHA**, branche `main`, PQC ML-DSA-65 |
| 4 nœuds | déjà alignés + timer `artcb-follow-main` 5 min (rapport 207) |
| Livre | height 1 (non vidé) |
| Biométrie | **absente de `main` avant ce tour** (seulement PR #52) |
| Badge `/health` | `certified_distributed_mainnet=false` |

## 2. Pourquoi ce n’est **pas** certified — ce n’est pas un oubli

Le protocole (que tu as verrouillé) est un **ET** :

```
certified = (DV-01…DV-07 tous PASS)
         ET live_BFT implémenté
         ET V-01…V-07 économiques locked
         ET OPERATOR_MAINNET_CERTIFICATION_GO = True
```

| Condition | État réel | Source |
|-----------|-----------|--------|
| DV-01 identité / TPM honnête | **PASS** | `validation/DV-01/RESULT.json` |
| DV-02 P2P hostile (flood/partition lettre C) | **PARTIAL** | RESULT 189 + D-043 : flood/chaos live pas fini |
| DV-03 protocol_version / genesis / network_id | **PASS** | RESULT |
| DV-04 4 nœuds même `last_hash` après TX | **PASS** (189) | RESULT — à reconfirmer après biométrie |
| DV-05 BFT settlement N=4 F=1 Q=3 | **PASS** (188) | RESULT ; scope = WorkID, pas PBFT `append_block` |
| DV-06 pannes (perte paquets, reboot) | **PARTIAL** | RESULT 189 |
| DV-07 hybride AND ML-DSA | **PASS** | RESULT |
| `LIVE_BFT_IMPLEMENTED` | **True** | `consensus_spec.py` |
| V-01…V-07 | **locked** D-043 | `ECONOMIC_V_LOCKED=True` |
| GO opérateur | **False** | constante explicite |

**Renommer le badge sans PASS DV-02/DV-06 serait un mensonge de protocole**, pas une certification.  
`/health` appelait `certification_gate()` **sans** lire les RESULT.json → il affichait les 7 DV comme manquants même pour ceux déjà PASS. Ce tour : `load_dv_verdicts()` pour que le health soit **honnête**.

Sim 208 (`scripts/run_sim208_dv02_dv06_live.py`) relance **maintenant** flood HTTP borné (64×4, pas SYN) + `tc netem` 25 % / 80 ms sur OVH4 puis restore. Les RESULT.json ne passent à PASS **que** si c’est mesuré.

## 3. Inscription biométrique — comment c’est codé

**Pas encore en production avant ce merge.** Code écrit dans PR #52 (D-055), porté ici.

### Ce qu’on a écrit (ARTCB, dans le dépôt)

| Fichier | Rôle |
|---------|------|
| `src/artcb/security/webauthn_protocol.py` | Options + vérif attestation / assertion WebAuthn (challenge, flags UP/UV, sign_count) |
| `src/artcb/security/webauthn_cose.py` | Mini décodeur CBOR + clé COSE ES256 (P-256). **Pas** la lib `@simplewebauthn` |
| `src/artcb/security/webauthn_store.py` | JSON `data/webauthn/credentials.json` + `face_unlock.json` (hashes seulement) |
| `src/api/webauthn_routes.py` | `/api/v1/auth/webauthn/*` et `/api/v1/auth/face/*` |
| `src/api/auth_routes.py` | `issue_session()` partagé (mot de passe / WebAuthn / caméra) |
| `frontend/src/lib/webauthn.ts` | Appel `navigator.credentials.create/get` |
| `frontend/src/pages/RegisterBiometric.tsx` | UI empreinte / visage / les deux |
| `frontend/src/components/FaceCapture.tsx` | Caméra + liveness **locale** |

### Ce qu’on n’a **pas** inventé (standards / OS, open)

| Techno | Origine | Licence / statut | Rôle exact |
|--------|---------|------------------|------------|
| **WebAuthn / Web Authentication** | W3C + FIDO Alliance | Standard ouvert | Le navigateur parle au capteur. L’empreinte / Face ID **ne quitte pas** l’appareil. Le serveur ne voit qu’une **clé publique** ES256 + une signature. |
| **Platform authenticator** | Apple Touch ID / Face ID, Windows Hello, Android | OS propriétaire, API standard | `authenticatorAttachment=platform` + `userVerification=required` |
| **pyca/cryptography** | Open source (Apache/BSD) | déjà dépendance | Vérif ECDSA P-256 |
| **FastAPI / Pydantic / React** | Open source | déjà dans le projet | HTTP + UI |
| **FaceDetector** (optionnel) | API navigateur Shape Detection | pas partout | Boîte englobante « un visage est dans le cadre » — **pas** un modèle ARTCB de reconnaissance faciale |
| **getUserMedia** | Standard navigateur | ouvert | Accès caméra avant |

Aucune image brute n’est acceptée par l’API (`raw_biometric_rejected`). Rien on-chain.

### Flux exact

1. **Empreinte / Face ID OS**  
   `POST …/webauthn/register/options` → le navigateur crée une credential platform → `register/verify` vérifie l’attestation → session `sess_` + wallet. Login = même chose en `get`.

2. **Caméra (handicap moteur, pas de Face ID)**  
   Le navigateur fait une liveness **sur l’appareil** (visage détecté). Le serveur reçoit seulement `liveness_ok=true` + un **secret d’appareil** (32 octets dans `localStorage`). Le serveur stocke `sha256(secret)`. Ce n’est **pas** de la biométrie serveur : c’est un déverrouillage appareil + preuve « un visage était dans le cadre ».

3. **Les deux** : empreinte d’abord, puis visage.

Tests machine : `tests/test_webauthn_biometric.py` (authenticator **logiciel**, pas un téléphone réel). Un vrai capteur n’est pas exercé dans CI.

## 4. Tests liés

| Suite | Attendu | Note |
|-------|---------|------|
| `test_e2e205_no_rescue_biometric.py` | pas de rescue, routes UI, `raw_biometric_rejected` | fichier |
| `test_e2e208_biometric_cert_gate.py` | gate honnête, GO false, stack WebAuthn | fichier |
| `test_webauthn_biometric.py` | register/login software | besoin FastAPI |
| `test_e2e207_follow_main.py` | 4 nœuds suivent main | déjà 4 passed |

## 5. Production

Ordre opérateur : pousser. Biométrie + health honnête → `main` → timer 5 min sur les 4 VM.  
Si ça casse (UI, CORS, WebAuthn rpId `artcb.me`), c’est **voulu maintenant**.

**Toujours pas certified** tant que DV-02/DV-06 ne sont pas PASS **mesurés** et que le GO n’est pas posé **après** ces PASS. Flipper le booléen avant = casser le protocole, pas le terminer.
