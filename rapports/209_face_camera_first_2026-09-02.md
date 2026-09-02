# Rapport 209 — Visage ouvrait le capteur OS, pas la caméra

**Horodatage :** 2026-09-02T21:40:00Z  
**Live SHA au constat :** `12b95841a7679c25091825d8f6e8b4b519a59462`

Rien d’inventé. Seed / PEM non recopiés ici.

## Ce qui s’est passé (mesuré)

L’utilisateur a testé « reconnaissance faciale ». Le **capteur biométrique** s’est allumé. **Aucune caméra.**

La chaîne 64 hex reçue est une **seed de wallet** (32 octets), affichée une seule fois après inscription (`bio_seed_once`). Elle dérive l’adresse **`artcb1auw5lhn2dfdjmdgk0em257fk2h74klvkfqcxkt`**.

Sur OVH1 `data/wallets/Gabriel.json` :

- `name=Gabriel`
- `address=artcb1auw5lhn2dfdjmdgk0em257fk2h74klvkfqcxkt`
- `auth_methods=['webauthn_fingerprint', 'webauthn_face']`

`data/webauthn/credentials.json` : 1 credential `fingerprint` + 3 `face`, toutes **WebAuthn platform** (`rp_id=artcb.me`, clé COSE, pas de hash caméra).  
`data/webauthn/face_unlock.json` : **absent** → le flux caméra n’a **jamais** tourné.

## Pourquoi (pas un capteur cassé)

WebAuthn `authenticatorAttachment=platform` demande au **système** (empreinte / Face ID / Windows Hello). Android et iPhone **ne peuvent pas** ouvrir la caméra selfie via `navigator.credentials.create`. C’est le même capteur que « Empreinte ».

L’ancien code faisait : bouton Visage → d’abord WebAuthn `face`. Si ça réussit (presque toujours s’il y a un capteur), la caméra en `catch` **ne part jamais**.

## Correctif

- Bouton **Visage** → caméra avant (`FaceCapture` / `getUserMedia`) tout de suite.
- **Empreinte** → capteur OS (WebAuthn), inchangé.
- **Les deux** → empreinte puis caméra.
- Connexion visage : caméra si `face_camera_enrolled` ; sinon repli WebAuthn pour les comptes déjà créés comme Gabriel.

Cette seed a été collée dans le chat : la traiter comme **exposée**. En créer une nouvelle si le wallet doit rester privé.
