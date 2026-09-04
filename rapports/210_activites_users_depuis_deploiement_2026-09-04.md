# Rapport d’activités utilisateurs — depuis le dernier déploiement

**Dépôt :** https://github.com/vgactech/artcb  
**Nature :** constat mesuré uniquement. Aucune modification du code. Ce rapport n’est **pas** le plan privacy.md (fichier séparé).

**Cutoff « dernier déploiement » retenu**

| Champ | Valeur mesurée |
|---|---|
| Commit déployé (PR #56 camera-first) | `990995380f1c2a4a8f549a51f939922d82d21371` |
| Message | `docs: T-E41 camera-first passé` |
| CommitDate | `2026-09-02T21:35:51Z` |
| PR GitHub | #56 merged `2026-09-02T21:35:44Z` |
| Instant d’observation de ce rapport | `2026-09-04` (après-midi UTC) |

Tout ce qui suit est **après** `2026-09-02T21:35:51Z`, sauf mention explicite « avant / déjà présent ».

**Live au moment de la mesure**

- Bootstrap OVH1 : HTTP 200, `git_sha=addc6e9e23e5da17701b0a63aba9b4ce62ec8140`, branche `main`.
- `origin/main` = le même SHA. Égalité live ↔ GitHub main : **oui**.
- `/health` : `status=healthy`, `certified_distributed_mainnet=True`, `operator_certification_go=True`, `network_id=artcb-mainnet-1`, `genesis_hash=genesis-artcb-mainnet-1`, `protocol_version=189-mainnet-1`, `release_integrity=ok`, `pqc` présent (ML-DSA-65 côté bootstrap).
- 4 nœuds officiels : HEAD identique `addc6e9`, `BOOK=1`, timer follow-main `enabled`, service `artcb` `active`.

Aucun solde, aucun contenu de seed/PEM/token n’est reproduit ici.

---

## 1. GitHub — ce qui a bougé après le déploiement camera-first

### 1.1 Commits sur `main` après `9909953`

Quatre commits, **même arbre git** que `9909953` (diff vide). Ce ne sont pas des changements de code.

| SHA court | Auteur | AuthorDate | CommitDate | Message |
|---|---|---|---|---|
| `9938514` | Replit Agent `<agent@replit.com>` | 2026-09-02T13:28:23Z | 2026-09-03T18:29:01Z | Published your App (build `abe4e9be-…`) |
| `08f0214` | Replit Agent | 2026-09-02T14:06:29Z | 2026-09-03T18:29:01Z | Published your App (build `fc3ffbf6-…`) |
| `705fdc4` | Replit Agent | 2026-09-02T14:29:00Z | 2026-09-03T18:29:01Z | Published your App (build `9bde33d9-…`) |
| `addc6e9` | Replit Agent | 2026-09-02T16:08:17Z | 2026-09-03T18:29:01Z | Published your App (build `aef0a4af-…`) |

**Constat**

- Committer git : `vgactech <vgacofficiel@gmail.com>`.
- Les quatre `CommitDate` sont **identiques** à la seconde (`2026-09-03T18:29:01Z`) : empilement Replit « Publish » d’un coup, après le merge camera-first.
- Les `AuthorDate` sont **antérieures** au merge #56 (après-midi du 2 sept.) mais n’apportent **aucun fichier**. `git rev-parse 9909953^{tree}` = `addc6e9^{tree}` = `8446c5c4d12b982cdb4c4ff63b2b67d2b0ea5d11`.
- Les 4 nœuds ont **suivi** ce SHA via follow-main (timer 5 min). Comportement produit inchangé par rapport à `9909953`.

### 1.2 Pull requests

Aucune PR **nouvelle** ouverte après #56 dans la liste observée. État autour du déploiement :

| # | Titre | État | Merged / MAJ |
|---|---|---|---|
| 56 | fix(ui): Visage = caméra avant | MERGED | 2026-09-02T21:35:44Z ← cutoff |
| 55 | biométrie WebAuthn + gate cert | MERGED | 2026-09-02T21:18:56Z |
| 54 | follow-main auto 4 nœuds | MERGED | 2026-09-02T20:25:02Z |
| 53 | docs OVH4 secrets | OPEN | 2026-09-02T19:44:50Z |
| 52 | SSH sans rescue + inscription biométrie | OPEN | 2026-09-02T19:23:51Z |
| 51 | OVH2 SSH rescue | DRAFT | 2026-09-02T19:05:20Z |

Issues GitHub avec `updated:>=2026-09-02` : **aucune** dans l’échantillon `gh issue list`.

### 1.3 Ce que ça veut dire pour « activités users »

Le seul mouvement git **après** le déploiement camera-first est **Replit Publish** sans diff. Pas de nouveau code utilisateur, pas de nouvelle issue.

---

## 2. Nœud OVH1 (`artcb.me` / `152.228.144.34`) — seuls vrais comptes wallet humains

Inventaire wallets / WebAuthn lu sur le nœud (mtime disque). `AFTER` = mtime ≥ cutoff.

### 2.1 Wallets

| Label | Adresse | Auth methods | Mtime | Par rapport au cutoff |
|---|---|---|---|---|
| Gabriel | `artcb1auw5lhn2dfdjmdgk0em257fk2h74klvkfqcxkt` | `webauthn_fingerprint`, `webauthn_face` | 2026-09-02T21:30:37Z | **juste avant** le commit `9909953` (21:35:51Z) — session d’enrôlement du jour du déploiement, pas créée *après* le SHA live actuel |
| Chaves | `artcb1vfpa6yuztpsqm5n2lumvqmwy3llfrrltj7w53m` | `webauthn_fingerprint`, `face_camera` | 2026-09-02T22:03:58Z | **après** |
| Victor | `artcb1gryn5eptl59pcduhg00kafksueetsx9ul3z765` | `webauthn_fingerprint` | 2026-09-02T22:05:37Z | **après** |
| testA | `artcb1rn92x9cytsp4gcj32kjlyj34xszs5rwqfx0n4h` | `face_camera` | 2026-09-03T19:47:23Z | **après** (lendemain) |
| cursor-cloud-agent | `artcb1cnclv0ulcrhjg3zcg0tw24ldtt74tdcgnsxs4p` | aucun | 2026-08-29T19:50:03Z | avant, hors période |

Répertoire `data/wallets` mtime global : `2026-09-03T19:47:23Z` (= création `testA`).

### 2.2 WebAuthn (fichier credentials)

- Fichier présent. Mtime `2026-09-02T22:05:37Z` (**après** cutoff) — cohérent avec Victor.
- **6** credentials, `signCount=0` partout (enregistrés, pas de preuve d’usage de signature WebAuthn en login après coup dans ce compteur).

| Wallet | Type | rpId |
|---|---|---|
| Gabriel | fingerprint ×1 | artcb.me |
| Gabriel | face ×3 | artcb.me |
| Chaves | fingerprint ×1 | artcb.me |
| Victor | fingerprint ×1 | artcb.me |

**Note :** Gabriel a encore des creds WebAuthn `face` (capteur OS) hérités d’avant le fix camera-first. Les nouveaux comptes Chaves/testA utilisent `face_camera`, pas `webauthn_face`.

### 2.3 Face caméra (`face_unlock.json`)

- Absent au moment du merge #56 (constat de session précédente). **Présent maintenant.**
- Mtime `2026-09-03T19:47:23Z`. **2** enregistrements, liveness=True, hash présent (pas d’image).

| Wallet | Liveness | Hash stocké |
|---|---|---|
| Chaves | True | oui |
| testA | True | oui |

Gabriel : **pas** d’entrée `face_unlock` (reste sur WebAuthn face OS). Victor : empreinte seulement.

### 2.4 Session HTTP humaine identifiable (nginx + journal uvicorn)

Source `195.220.106.83`, UA `Chrome/128` `X11 Linux`, Referer `https://artcb.me/` — **seul trafic qui ressemble à un utilisateur réel du site**, pas un scanner.

| Heure UTC | Requête | Code | Lecture |
|---|---|---|---|
| 2026-09-03 19:46:11 | `POST /api/v1/auth/login` | **401** | tentative login (échec) |
| 19:46:52 | idem | 401 | |
| 19:46:56 | idem | 401 | |
| 19:47:00 | idem | 401 | 4 échecs d’affilée |
| 19:47:23 | `POST /api/v1/auth/face/enroll/options` | **200** | démarre enrôlement caméra |
| 19:47:23 | `POST /api/v1/auth/face/enroll/verify` | **200** | enrôlement **réussi** |
| 19:51:47 | `GET /api/v1/wallet/list` | 200 | liste wallets (journal artcb) |

**Croisement :** 19:47:23 = mtime exact du wallet `testA` + `face_unlock.json`. Donc : une personne (ou un navigateur opérateur) a **échoué le login mot de passe/session**, puis a **créé `testA` via la caméra** sur artcb.me, le 3 sept. ~19:47 UTC.

Pas d’autre `POST /api/v1/auth/*` 200 humain vu dans l’extrait nginx OVH1 après cette fenêtre.

### 2.5 Lectures `GET /api/v1/wallet/list` (pas forcément « user produit »)

Journal artcb OVH1 après cutoff :

| Heure | Source | Lecture probable |
|---|---|---|
| 2026-09-03T19:51:47Z | 195.220.106.83 | même session que testA |
| 2026-09-04T05:48:52Z | 34.122.147.229 | Google Cloud — agent / sonde, pas un parcours UI |
| 2026-09-04T07:04:55Z et 07:04:59Z | 62.210.198.197 | Scaleway — typique Cloud Agent / sonde |

Ces GET 200 listent les wallets ; ce n’est pas un enrôlement.

### 2.6 Journal processus

- `WalletManager initialized` aux heures des listes ci-dessus.
- `Invalid HTTP request received` répété (4 sept. 04:04, 06:08, 10:47–14:05) : clients non-HTTP/1.1 ou TLS mal formé — **scanners**, pas l’UI.
- Pas d’événement d’append_block / mint / settlement dans l’extrait journal fourni.

---

## 3. Nœud OVH2 (`n2.artcb.me` / `151.80.107.29`)

### 3.1 Comptes

- Un wallet `ovh-node-2` (`artcb1ykchmlksgnt6qmgez7u6pfecgwl5mn96xmsr9z`), mtime **2026-08-31** — **aucun nouvel utilisateur**.
- WebAuthn : absent. Face unlock : absent.

### 3.2 HTTP après cutoff

- Pas de `POST /api/v1/auth/*` ni face enroll.
- Trafic = scanners (voir §6) + GET login-like via `127.0.0.1` (proxy local / autre sonde) le 4 sept. 10:52–10:53 et 14:11.

**Activité user produit : nulle.**

---

## 4. Nœud AWS3 (`n3.artcb.me` / `51.44.222.232`)

### 4.1 Comptes

- Wallet `aws-node-3` uniquement, mtime **2026-08-31**. Pas de WebAuthn / face.

### 4.2 Ops (pas un user métier)

- **2026-09-03T18:31:59Z** : arrêt uvicorn PID 228173 puis **redémarrage** PID 251576 à 18:32:00 — calé sur le `CommitDate` Replit `18:29:01Z` (follow-main a tiré `addc6e9`, restart service).
- Au boot : TenSEAL absent (mode homomorphe simulé, warning journal) ; FAISS AVX messages ; `wallets_active=0` sur ce nœud ; seed_discovery `directory=4 peers_added=0 errors=3` (connexion refused au moment du boot — les pairs pas encore up).
- `GET /api/v1/wallet/list` 200 depuis `205.169.39.185` (3 sept. 12:01) et `205.169.39.6` (4 sept. 07:47) — plage Cursor/GCP, **sondes agent**, pas d’enrôlement.

**Activité user produit : nulle.**

---

## 5. Nœud OVH4 (`n4.artcb.me` / `91.134.45.8`)

### 5.1 Comptes

- Wallet `ovh-node-4` uniquement, mtime **2026-08-31**. Pas de WebAuthn / face.

### 5.2 HTTP

- 3 sept. 22:10–22:12 : `45.148.10.123` envoie des **POST** `/login`, `/register`, `/api/auth/signin`, `/auth/callback` → **405** (l’API n’expose pas ces routes ainsi). Pattern credential-stuffing / scanner, **pas** l’UI ARTCB (`/api/v1/auth/...`).
- Reste : OWA / GlobalProtect / login.jsp (scanners).

**Activité user produit : nulle.**

---

## 6. Bruit Internet (à ne pas compter comme utilisateurs ARTCB)

Vu sur plusieurs nœuds, surtout OVH1 et OVH2.

### 6.1 `213.209.159.175`

Balayage répétitif `GET //register`, `/register/.env`, `/auth/.env`, `/error.log`, `/wp-login.php`, etc.

- Nginx OVH1 répond souvent **200** avec **777 octets** = **shell SPA** (index), **pas** un fichier `.env` réel.
- Sur `/auth/.env` via nginx parfois **404** (34.34.225.165 le 3 sept. 16:53, chemins `/auth/.git/config` etc.).

Fréquence : toutes les ~2–3 h du 3 sept. 07:13 au 4 sept. 11:51.

### 6.2 Autres scanners

| Source | Quoi | Nœuds |
|---|---|---|
| 34.34.225.165 | phpinfo, `.git/config`, `.env*` | OVH1 → 404 |
| 20.102.108.180 / 20.84.164.199 / zgrab | `/owa/auth/x.js` | OVH1, AWS3 |
| 134.209.58.171, 137.184.77.90 | pantheon login paths (OWA, Dana, sslvpn, …) | OVH2, OVH4 |
| 45.148.10.123 | POST login/register 405 | OVH4 |
| 66.132.195.103 | GET `/login` | OVH2 |
| 104.207.59.34 / 138.197.221.54 | POST GlobalProtect prelogin **405** | AWS3, OVH4 |

`Invalid HTTP request received` (uvicorn) = même famille (HTTP malformé / HTTPS sur HTTP).

---

## 7. Synthèse point par point — ce qui s’est **vraiment** passé côté users

1. **Déploiement de référence** : PR #56 camera-first, SHA `9909953`, 2026-09-02T21:35Z, 4 nœuds ensuite alignés.
2. **Git après coup** : 4 tags Replit « Published your App » le 2026-09-03T18:29Z, **arbre identique**, restart AWS3 18:32Z. Pas de feature nouvelle.
3. **Comptes nouveaux après le SHA camera-first**
    - **Chaves** : 2026-09-02T22:03:58Z — empreinte WebAuthn + face **caméra**.
    - **Victor** : 2026-09-02T22:05:37Z — empreinte WebAuthn seulement.
    - **testA** : 2026-09-03T19:47:23Z — **uniquement** face caméra, après 4× login 401.
4. **Gabriel** : wallet déjà là à 21:30:37Z le 2 sept. (minutes **avant** le commit docs T-E41). Toujours `webauthn_face` ×3 + fingerprint ; **pas** migré vers `face_camera`.
5. **Login réussi par mot de passe** : **non observé** (seulement 401 puis enroll face pour testA).
6. **Usage WebAuthn `signCount`** : toujours 0. **Correction de lecture :** un authenticator plateforme (Android/Apple) peut rester à 0 même après login. La preuve plus forte est nginx : **zéro** `webauthn/login` ni `face/login` dans `access.log` + `access.log.1`.
7. **Nœuds 2, 3, 4** : aucun wallet humain nouveau ; seulement wallets de nœud d’août.
8. **Issues / PRs user** : rien de nouveau après #56.
9. **Chaîne / mint / settlement** : **non attestés** dans les extraits journal de cette fenêtre (pas inventé).
10. **Certification live** : toujours `certified_distributed_mainnet=True` / `operator_certification_go=True` au SHA `addc6e9`.

---

## 8. Limites de ce rapport

- `access.log` + `access.log.1` relus en entier pour `webauthn/login` et `face/login` (résultat vide). Le reste du trafic hors auth peut manquer.
- Pas de lecture de `blocks.jsonl` (interdit d’inventer une hauteur).
- Le journal n’enregistre **pas** le nom de wallet sur un `/auth/login` 401 : on ne sait pas si testA a tapé `Gabriel`, `testA` ou autre.
- Identité civile non établie ; IPs seulement.

---

## 9. Relecture — bugs et anomalies (2026-09-04)

**Réponse directe :** non, le premier jet n’était pas « zéro anomalie ». Les quatre comptes sont réels ; plusieurs **écarts produit / sécurité** sont mesurés autour d’eux. Rien n’a été « inventé » : journal + nginx + code.

### 9.1 Gabriel — pas un nouveau user après #56, mais un bug d’enrôlement encore visible

Source IP **`85.69.218.227`** (pas la même que testA).

| UTC | Événement |
|---|---|
| 21:29:28 | `POST .../webauthn/register/options` 200 |
| 21:29:33 | `Biometric wallet created name=Gabriel` + register/verify 200 |
| 21:29:33–21:29:43 | 2ᵉ register options+verify |
| 21:30:21–21:30:27 | 3ᵉ |
| 21:30:31–21:30:37 | 4ᵉ |

= 1 fingerprint + **3** creds `modality=face` (capteur OS). Cause déjà connue (bouton Visage → WebAuthn platform **avant** le fix camera-first, mergé 21:35). `save_credential()` déduplique par `credential_id` seulement, **pas** par `(wallet, modality)` → les 3 face s’empilent.

**Anomalie persistante :** pas d’entrée `face_unlock.json` pour Gabriel. Login « Visage » actuel tombe en fallback WebAuthn OS si `face_camera_enrolled` est faux.

### 9.2 Chaves — pas un bug, parcours « les deux » **après** camera-first

Même IP `85.69.218.227`, **après** `9909953` :

| UTC | Événement |
|---|---|
| 22:03:46–22:03:50 | WebAuthn register + `Biometric wallet created name=Chaves` |
| 22:03:58 | `face/enroll/options` + `verify` 200 (caméra) |

C’est le bouton **les deux** du code post-#56 (`handleRegister("both")`). Cohérent. Pas d’anomalie ici.

### 9.3 Victor — pas un bug

22:05:34–22:05:37, même IP, **un seul** WebAuthn register (empreinte). Il n’a pas enchaîné la caméra.

### 9.4 testA — 401 mot de passe puis caméra : trou produit, pas un scanner

IP **`195.220.106.83`** (autre machine que Gabriel/Chaves/Victor).

| UTC | Événement |
|---|---|
| 19:45:32, 19:45:53 | `GET /api/v1/wallet/list` 200 (réponse **17562** octets) |
| 19:46:11 … 19:47:00 | **4×** `POST /api/v1/auth/login` **401** (page Wallets : `authLogin` / bouton Activer — la page biométrie **n’appelle jamais** `/auth/login`) |
| 19:47:23 | `face/enroll` 200 + `Biometric wallet created name=testA` |
| 19:48:27+ | `wallet/list` 200, taille **21936** (+ testA) |
| 19:50:12 | `GET /api/v1/api-keys/list` **401** (la session `sess_` de l’enrôlement n’est **pas** une API key) |

`/auth/login` déchiffre le `.key` avec le mot de passe utilisateur. Or `_create_wallet_if_needed` pose un `vault = secrets.token_urlsafe(32)` **jamais montré comme mot de passe** (seul `seed_hex` l’est une fois). **Activer / login mot de passe sur un wallet biométrique échoue toujours**, même pour le propriétaire. Les 4× 401 collent à ça (ou à un nom inexistant — le 401 est le même message `"Identifiants invalides"`).

### 9.5 Personne n’a **revérifié** l’identité après l’enrôlement

`grep` nginx `webauthn/login` et `face/login` sur `access.log` + `access.log.1` : **aucune ligne**.  
Les quatre humains se sont **inscrits**. Aucun login biométrique ultérieur n’apparaît dans les logs retenus. Ce n’est pas `signCount=0` qui le prouve (les capteurs OS laissent souvent 0) ; ce sont les **routes de login jamais hit**.

### 9.6 `GET /api/v1/wallet/list` public — anomalie de confidentialité sur ces users

`src/api/routes.py` `wallet_list` : **pas de Bearer**. Dump de **tout** le JSON metadata (`name`, `address`, `address_v2`, `auth_methods`, `public_key_hex`, `pqc_public_key_hex` ~3,9 ko, `has_key_file`).

Mesuré : 200 depuis artcb.me, Applebot, Chrome desktop/mobile, et la session testA. Taille 17–22 ko. Les prénoms **Gabriel / Chaves / Victor / testA** et leurs adresses sont listables par n’importe qui. `has_key_file=true` dit en plus que la seed chiffrée est **sur ce nœud**.

Ce n’est pas une fuite de seed. C’est une **énumération** des comptes réels.

### 9.7 Ce qui n’est **pas** un bug

- Chaves empreinte + caméra : parcours voulu post-#56.
- Victor empreinte seule : choix UI.
- testA caméra seule : bouton Visage post-#56 (correct).
- 200 sur `GET /register/.env` : SPA 777 octets, pas un `.env`.
- `signCount=0` tout seul : insuffisant pour crier « jamais reconnecté ».

### 9.8 Gravité (pour décider un fix plus tard — **pas fait dans ce push**)

| id | Gravité | Où |
|---|---|---|
| A | Haute (privacy) | `/wallet/list` sans auth |
| B | Haute (UX / lockout) | wallets biométriques inactivables via mot de passe / Activer |
| C | Moyenne | Gabriel : 3× `webauthn_face` orphelins, pas de caméra |
| D | Moyenne | `save_credential` n’écrase pas l’ancienne modality |
| E | Basse (observabilité) | 401 login sans nom de wallet dans le journal |
| F | Basse | `api-keys/list` 401 après enroll (session ≠ API key) — attendu, mal guidé |

---

## 10. Fichiers

- `rapports/210_activites_users_depuis_deploiement_2026-09-04.md`
- Plan croisé (autre fichier) : `rapports/211_plan_integration_privacy_md_artcb_2026-09-04.md`
