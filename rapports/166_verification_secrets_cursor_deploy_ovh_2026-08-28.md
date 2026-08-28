# Rapport 166 — Vérification des secrets Cursor et tentative de déploiement OVH

**Horodatage UTC :** 2026-08-28T22:22:00Z  
**Branche de travail :** `cursor/tokenomics-21m-hbp-owner-decay-3fcb` (aucun merge `main` par cet agent)  
**HEAD local / `origin` branche :** `76ed77b5abb8d0e15c2b1cfc78a3f7b4380be2a5`  
**Run Cursor :** `bc-1b370212-8a64-569b-90cc-e3ee5e273282` (« Vérifier secrets et déployer OVH »)  
**Compare :** https://github.com/vgactech/artcb/compare/main...cursor/tokenomics-21m-hbp-owner-decay-3fcb  
**Preuves HTTP :** `logs/20260828_ovh_live_secrets_verify.txt`  
**Preuves auth (noms / codes HTTP seulement) :** `logs/20260828_secrets_auth_probe.txt`  
**Aucune valeur secrète** dans ce rapport, les logs, ni git.

**DEBUG ON.** Ne pas écraser 160–165.

---

## 0. Réponse à « j’ai pourtant tout intégré dans les secret cursor »

**Les 6 secrets Cursor nommés sont bien injectés dans CE pod.** Ce n’est pas un problème d’`environment.json` manquant (ce run n’a **pas** d’environnement lié : `environment-info.environment = null`). L’injection vient des **Cloud Agent Secrets** du dashboard.

En revanche :

1. **Aucune clé SSH** n’est nommée dans Cursor → déploiement impossible.  
2. `DOPPLER_TOKEN` est injecté mais **rejeté** par Doppler (HTTP **401**).  
3. Le triplet OVH signe correctement avec la formule officielle, mais `OVH_CONSUMER_KEY` est **morte** (HTTP **403** « This credential does not exist »).

Intégré dans Cursor ≠ accepté par Doppler / OVH / SSH.

---

## 1. Table des noms (pas les valeurs)

Source runtime : `CLOUD_AGENT_ALL_SECRET_NAMES` = `CLOUD_AGENT_INJECTED_SECRET_NAMES` (6 noms, tous injectés).

| Nom Cursor | Dans le dashboard | Injecté ici | Longueur | Issue |
|------------|-------------------|-------------|----------|--------|
| `DOPPLER_TOKEN` | oui | oui | 53 | HTTP **401** Invalid Auth token |
| `OVH_APPLICATION_KEY` | oui | oui | 16 | format hex OK ; couple app **accepte** la signature officielle |
| `OVH_APPLICATION_SECRET` | oui | oui | 32 | idem |
| `OVH_CONSUMER_KEY` | oui | oui | 32 | HTTP **403** credential does not exist |
| `OVH_CLOUD_PROJECT_ID` | oui | oui | 32 | inutilisable sans CK valide |
| `OVH_ENDPOINT` | oui | oui | 6 | `ovh-eu` (pas un secret) |
| `OVH_SSH_PRIVATE_KEY` | **non** | **non** | — | **absent** |
| `SSH_PRIVATE_KEY` | **non** | **non** | — | **absent** |
| `ARTCB_SSH_KEY` | **non** | **non** | — | **absent** |
| `STRIPE_SECRET_KEY` | non | non | — | hors scope deploy SSH |

Fichiers : `~/.ssh/` = seulement `known_hosts`. Pas de `/cursor/secrets`, pas de `~/.doppler`, pas de clé écrite par l’agent frère `bc-6fca082f-dfe1-4d72-957b-624c389a3fcb` (« Clés OVH et secrets Doppler », statut `WAITING_FOR_BACKGROUND_WORK`, `environment=null`).

`DOPPLER_TOKEN` : préfixe de **type** service token (`dp.st.…`, 4 segments, sans whitespace). Le format est plausible ; Doppler le refuse quand même. **Ne pas recoller un ancien token** déjà 401.

---

## 2. Doppler

| Appel | Résultat |
|-------|----------|
| `GET https://api.doppler.com/v3/workplace` `Authorization: Bearer` | **401** `Invalid Auth token` |
| `GET /v3/me`, `/v3/auth/me` | **401** |
| En-têtes alternatifs (`token`, `apiKey`, `X-Doppler-Token`) | **401** (pas d’api key / token invalide) |
| CLI `doppler` | non installé (API HTTP utilisée à la place) |

Impossible de lister les noms Doppler (`OVH_SSH_PRIVATE_KEY` côté Doppler non vérifiable). **Aucun secret Doppler n’a été imprimé.**

Action utilisateur : Doppler → projet `artcb-blockchain` → Access → **nouveau** Service Token lecture → remplacer **exactement** le secret Cursor nommé `DOPPLER_TOKEN` (coller sans guillemets, sans retour ligne). Relancer un agent **après** la sauvegarde.

---

## 3. API OVH

Rapport 165 : « Invalid signature ». **Cause script**, pas (seulement) des clés.

Formule **officielle** OVH : `$1$` + SHA1(`AS + CK + METHOD + URL + BODY + TS`) — **sans** Application Key.  
`scripts/check_ovh.py` signe encore `AK+AS+CK+…` → **400 Invalid signature** (reproduit ici).  
Formule officielle + mêmes secrets Cursor → **403 This credential does not exist**.

| Appel | Formule | HTTP | Message |
|-------|---------|------|---------|
| `/auth/time` | aucune | 200 | delta 0 s |
| `GET /me` | officielle | **403** | This credential does not exist |
| `GET /me` | legacy (+ AK) | **400** | Invalid signature |
| `GET /cloud/project` | officielle | **403** | This credential does not exist |
| `GET /auth/currentCredential` | officielle | **403** | This credential does not exist |

Interprétation : Application Key + Secret sont un couple HMAC **cohérent** (sinon 400 signature aussi en formule officielle). La **Consumer Key** Cursor n’existe plus (révoquée / expirée / mauvais coller). Pas d’injection de clé SSH via l’API.

Action utilisateur : créer une **nouvelle** CK (validation SSO OVH, règles **sans tabulation** — cf. rapport 123), puis remplacer le secret Cursor `OVH_CONSUMER_KEY`. Cela **ne déploie pas** : il faut aussi la clé SSH.

---

## 4. SSH → `152.228.144.34`

Script : `scripts/deploy_ovh.sh` → utilisateur `ubuntu` (puis essais `debian`, `root`).

| Cible | Port 22 | Auth |
|-------|---------|------|
| `ubuntu@152.228.144.34` | OpenSSH_9.6p1 | **255** Permission denied (publickey) |
| `debian@…` | idem | **255** publickey |
| `root@…` | idem | **255** publickey |

Aucune identité privée offerte (`id_rsa` / `id_ed25519` type `-1`).  
`deploy_ovh.sh` **non exécuté** jusqu’au `git checkout` distant (SSH meurt avant).

Action utilisateur : ajouter dans Cursor Secrets **un** de :

- `OVH_SSH_PRIVATE_KEY` (nom documenté rapport 123, clés `artcb-deploy` / `artcb-cloud-agent-20260819` déjà dans `authorized_keys` de la box), ou  
- `SSH_PRIVATE_KEY` / `ARTCB_SSH_KEY`  

PEM complet (`BEGIN … PRIVATE KEY`), newlines réels, pas de passphrase si possible. **Ne pas** coller la clé dans le chat.

---

## 5. Live OVH — cette branche n’est PAS servie

Public : `http://152.228.144.34:8000`  
Preuve : `logs/20260828_ovh_live_secrets_verify.txt` (UTC 20260828T222058Z)

| URL | HTTP | Contenu |
|-----|------|---------|
| `GET /health` | **200** | healthy, v0.3.0, PQC ML-DSA-65, **pas** de `git_sha` |
| `GET /api/v1/health` | **200** | chain valid, **0** blocs, hybrid ML-DSA-65, `bob_configured=true`, **pas** de `git_sha` |
| `GET /api/v1/economics/` | **404** | Not Found |
| `GET /api/v1/economics/params` | **404** | |
| `GET /api/v1/economics/h-adult` | **404** | |
| `GET /api/v1/mining/protocol` | **404** | |
| `GET /api/v1/mining/protocol/status` | **404** | |

Health 165 (`src/artcb/release.py`) exposerait `git_sha` + `git_branch` **une fois** le code déployé. La box live = image **antérieure**.

| Réf | SHA |
|-----|-----|
| HEAD branche (GitHub + local au probe) | `76ed77b5abb8d0e15c2b1cfc78a3f7b4380be2a5` |
| SHA live OVH | **inconnu** (payload sans `git_sha`) ; routes 165 absentes → **pas** ce HEAD |

---

## 6. PR #34 — non touchée par cet agent

Consigne : ne pas merger PR #34 / `main`. **Respectée.**

Constat GitHub (lecture `gh`, hors de cet agent) : PR #34 **MERGED** le **2026-08-28T22:19:50Z** par `vgactech`, merge commit `532b1e5cf1e3b00774476bea9c8f91714e6270b4`. `origin/main` contient désormais `76ed77b`.

Cet agent **n’a pas** mergé. Body PR non modifié (`ManagePullRequest` absent ; `gh` lecture seule ; 165 : « not agent-managed »).

La box OVH n’a **pas** suivi ce merge : economics/mining restent 404.

---

## 7. Noms exacts à corriger dans Cursor Secrets

Déjà présents (à **remplacer** les valeurs, pas les noms) :

- `DOPPLER_TOKEN` — token **neuf** Doppler, test : HTTP 200 sur `/v3/workplace`
- `OVH_CONSUMER_KEY` — CK **neuve** validée SSO
- garder `OVH_APPLICATION_KEY` / `OVH_APPLICATION_SECRET` / `OVH_CLOUD_PROJECT_ID` / `OVH_ENDPOINT` s’ils n’ont pas été rotatés

**À ajouter** (absent du dashboard — bloquant deploy) :

- `OVH_SSH_PRIVATE_KEY` (préféré, doc 123) **ou** `SSH_PRIVATE_KEY`

Pas d’appel `request-environment-setup-actions` (ce run n’est pas un workflow `/env-setup`).

Après sauvegarde des secrets : **nouvel** agent (les pods déjà démarrés ne reçoivent pas les valeurs mises à jour).

---

## 8. Décision

**OVH ne sert pas cette branche.** Deploy SSH/Doppler/API OVH **échoué**. Aucun secret inventé. PR #34 non mergée par l’agent. Branche de travail inchangée (pas de merge `main` ici).
