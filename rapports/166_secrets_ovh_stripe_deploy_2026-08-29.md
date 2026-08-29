# Rapport 166 — Secrets Cursor corrigés, déploiement OVH réel, Stripe test live

**Horodatage UTC :** 2026-08-29T18:25:00Z  
**Branche :** `cursor/ovh-deploy-stripe-secrets-475d`  
**Base :** `main` = `532b1e5` (PR #34 **déjà mergée** par l’utilisateur)  
**HEAD au moment du rapport :** à tamponner après commit docs  
**Langue :** rapport FR, code EN. DEBUG ON.  
**Ne jamais écraser** 160–165. Simulations 164/165 **conservées**.

**607 verts ≠ protocole complet.** Pas d’oracle production-secure. Pas de certification multi-nœuds. API OVH HMAC toujours invalide.

---

## 0. Mission

Vérifier les secrets Cursor mis à jour (Doppler + Stripe), terminer le travail **bloqué** (SSH / Doppler / OVH / Stripe live), déployer **cette** branche sur artcb-node-1 **sans attendre un nouveau merge main**, notifier tous les problèmes rencontrés.

Expertises : audit secrets (métadonnées seulement), SSH, Doppler, Stripe test-mode, systemd, tokenomics live, pytest.

---

## 1. Secrets Cursor — état réel de CE runtime

Noms injectés (`CLOUD_AGENT_INJECTED_SECRET_NAMES`) :

`DOPPLER_TOKEN`, `KEY_API_STRIPE`, `OVH_APPLICATION_KEY`, `OVH_APPLICATION_SECRET`, `OVH_CLOUD_PROJECT_ID`, `OVH_CONSUMER_KEY`, `OVH_ENDPOINT`

**Aucune valeur n’est reproduite ici.**

| Nom attendu par les sessions 164–165 | Présent ? | Résultat |
|--------------------------------------|-----------|----------|
| `DOPPLER_TOKEN` | **oui** `dp.st.dev…` len=53 | **HTTP 200** `/v3/me` — service token `artcb-node-1`, workplace `lvxsecret`, projet `artcb-blockchain` |
| `KEY_API_STRIPE_ACTION` | **non** | Le secret réel s’appelle **`KEY_API_STRIPE`** (`rk_test…` len=107) |
| `KEY_API_STRIPE` | **oui** | `/v1/balance` 200 `livemode=false` ; PaymentIntent create+cancel **OK** |
| `OVH_SSH_PRIVATE_KEY` | **non** | La clé utile est Doppler **`SSH_PRIVATE_KEY`** (OpenSSH PEM, 7 lignes) |
| `OVH_APPLICATION_KEY/SECRET` | oui | **≠** la paire Doppler (hashes distincts) |
| `OVH_CONSUMER_KEY` | oui | **identique** à Doppler |

### 1.1 Doppler vs Cursor (hashes seulement)

- `OVH_APPLICATION_KEY` Cursor ≠ Doppler  
- `OVH_APPLICATION_SECRET` Cursor ≠ Doppler  
- `OVH_CONSUMER_KEY` Cursor = Doppler  
- Doppler a aussi `OVH_CONSUMER_KEY_NEW` et `OVH_CONSUMER_KEY_EXPIRED` (non testés comme valides — HMAC invalide dans tous les cas)

### 1.2 Token Doppler pour Replit

**Je ne peux toujours pas coller un token.** Un service token n’est visible qu’à la création. Le token Cursor actuel **fonctionne** (prouvé `/v3/me` 200). Pour Replit : créez un **second** service token Read (ex. `replit-dev`) et collez-le dans Replit → Secrets → `DOPPLER_TOKEN`. Ne réutilisez pas le token serveur/Cursor si vous voulez pouvoir en révoquer un sans casser les autres.

---

## 2. Problèmes rencontrés en cours de route (aucun masqué)

| # | Problème | Impact | Action / statut |
|---|----------|--------|-----------------|
| P1 | `KEY_API_STRIPE_ACTION` absent ; nom réel `KEY_API_STRIPE` | Tests Stripe skipés dans 164–165 | Code accepte les deux noms |
| P2 | `OVH_SSH_PRIVATE_KEY` absent Cursor | SSH impossible dans 165 | Clé lue depuis Doppler `SSH_PRIVATE_KEY` → `~/.ssh/artcb_ovh_deploy` 600 |
| P3 | Doppler `OVH_SERVER_IP=51.255.22.253` `OVH_SERVER_USER=root` | SSH timeout:22 ; ports 80/443/5000/8080 ouverts | **Pas** le nœud live. Live = `ubuntu@152.228.144.34` |
| P4 | API OVH HMAC `Invalid signature` (toutes les paires Cursor/Doppler AK/AS × CK/CK_NEW) | Pas de reboot d’instance via API | SSH suffit pour déployer. **À corriger côté console OVH** (paire app + consumer validée ensemble) |
| P5 | `git fetch origin <branche>` sans créer la branche locale | Premier `deploy_ovh.sh` : `pathspec did not match` | Box **restée** sur l’ancienne branche (service encore up). Script corrigé : `checkout -B` depuis `origin/` |
| P6 | Token Doppler **sur le serveur** (`/etc/artcb/doppler.env`) **Invalid Auth** | Après checkout : crash loop systemd (`Unable to download secrets`) ~30 s | Token serveur = ancien, probablement révoqué quand le token Cursor a été régénéré. Remplacé par le token Cursor valide (root 600). Service relancé |
| P7 | `install.sh` a recréé un `.env` d’exemple | Risque passphrase vide si Doppler KO | Script de deploy **supprime** `.env` si `doppler.env` existe |
| P8 | `GET /api/v1/mining/protocol` = 404 | Fausse alarme | La route est **POST** `/api/v1/mining/protocol` ; `GET …/protocol/status` = 200 |
| P9 | `liboqs-python` absent dans le venv de cet agent | PQC non rejoué ici | Box OVH : `pqc.available=true` ML-DSA-65 |
| P10 | PR GitHub automatique | `must be a collaborator` | Compare : https://github.com/vgactech/artcb/compare/main...cursor/ovh-deploy-stripe-secrets-475d |
| P11 | `node_identity` log : public_url `8000 → 5000` | Cosmétique / identité P2P | Doppler a encore des reliquats Replit (port 5000). Uvicorn écoute bien **8000** |
| P12 | Même token Doppler Cursor **et** serveur | Révoquer Cursor casserait OVH | Créer un token **dédié serveur** (`artcb-node-1`) et un token Cursor séparé |

---

## 3. OVH — avant / après

Public : `http://152.228.144.34:8000`  
Preuves : `logs/20260829_ovh_live_predeploy.txt`, `logs/20260829_ovh_live_postdeploy.txt`

### Avant (box 10 jours, branche `cursor/deploy-ovh-artcb-node-6526` @ `b62b6c93`)

| URL | HTTP | Contenu |
|-----|------|---------|
| `/health` | 200 | healthy v0.3.0, PQC, **pas** de `git_sha` |
| `/api/v1/health` | 200 | chain valid, 0 blocs, `bob_configured=true` |
| `/api/v1/economics/params` | **404** | code 164–165 absent |
| `/api/v1/mining/protocol/status` | **404** | |

### Après (cette branche @ `deaf620` puis HEAD 166)

| URL | HTTP | Contenu |
|-----|------|---------|
| `/health` | 200 | `git_sha`, `git_branch=cursor/ovh-deploy-stripe-secrets-475d`, PQC ML-DSA-65 |
| `/api/v1/health` | 200 | idem + `bob_configured=true` (Doppler live) |
| `/api/v1/economics/params` | **200** | 21 M, `halving_removed=true`, R(H), HBP 10→60→20, M1=100 % |
| `/api/v1/economics/h-adult` | **200** | `h_adult=0`, `hmax_frozen=false`, adult_max estimé 5,82e9 |
| `/api/v1/economics/emission?verified_humans=5` | **200** | `r_h_artcb=50`, `issued_artcb=50` |
| `/api/v1/economics/hbp?verified_humans=5` | **200** | ~10 % |
| `/api/v1/economics/owner-share?machine_index=1&n_economic=5` | **200** | `owner_share=1.0`, `fleet_p_extras=0.47074375` |
| `/api/v1/mining/protocol/status` | **200** | `wired=true`, `c_economic_root_abi=true` |

**SSH :** `ubuntu@152.228.144.34` OK (OpenSSH_9.6p1). Hostname `artcb-node-1`.

---

## 4. Stripe — tests réels (test-mode, jamais capture)

Secret : `KEY_API_STRIPE` = restricted key `rk_test` (jamais loggée).

| Test | Résultat |
|------|----------|
| `GET /v1/balance` | 200, `livemode=false` |
| Local `scripts/stripe_job_payment_ci.py` | `ok=true`, `mints=false`, status `canceled`, PI créé puis annulé |
| OVH `POST /api/v1/economics/jobs/priority` | 200, `kind=JobPayment`, `mints=false`, `distinct_from=R_block`, PI `canceled` |

**Stripe en panne ≠ chaîne en panne** : déjà testé en 165 ; inchangé. Le succès live ici **ne rend pas** Stripe une dépendance consensus.

GitHub Actions attend encore `KEY_API_STRIPE_ACTION` — à ajouter dans Settings → Secrets si vous voulez le même test en CI.

---

## 5. Pytest (cet agent)

Commande : `.venv` + `PYTHONPATH=src python3 -m pytest tests/ -q --tb=line`  
Log : `logs/20260829_pytest_rapport166.txt`

**607 passed, 8 skipped, 0 fail** (289,57 s).

Écart vs 165 (606 / 9 skip) : un test Stripe **exécuté** (secret présent) au lieu d’être skippé. PQC liboqs-python **absent** ici → skips PQC inchangés.

---

## 6. Code modifié (avant / après)

### `src/artcb/payments/stripe_jobs.py`

**Avant :** lecture seulement `KEY_API_STRIPE_ACTION` / `STRIPE_SECRET_KEY` / `STRIPE_API_KEY`.  
**Après :** + `KEY_API_STRIPE` (Cursor / Doppler). Constante `STRIPE_SECRET_ENV_NAMES`.

### `scripts/deploy_ovh.sh`

**Avant :** `git checkout "$BRANCH"` (échoue si la branche locale n’existe pas) ; IP par défaut pouvait suivre Doppler.  
**Après :** `git checkout -B` depuis `origin/` ou `FETCH_HEAD` ; IP live forcée `152.228.144.34` ; charge `SSH_PRIVATE_KEY` Doppler ; attend la santé.

### `scripts/start_node.sh`

**Avant :** `doppler run` dès que `DOPPLER_TOKEN` est non vide → crash si token révoqué.  
**Après :** `doppler me` d’abord ; si rejeté → fallback `.env` + message clair.

### `scripts/load_ovh_ssh_from_doppler.py`

**Nouveau.** Écrit la clé, mode 600, **n’imprime jamais** le PEM.

---

## 7. Ce qui n’est toujours pas fait (protocole)

Identique à 165, inchangé par ce déploiement :

1. `hmax_frozen=false` — chiffre ONU 18+ non gelé (Q-E03)  
2. Finder Q=100 / HumanID **pas** pipeline mining production  
3. Oracle prix **pas** multi-source / consensus  
4. Multi-nœuds distribués : scaffold seulement  
5. Ancres HBP 4,15e9 / 8,3e9 encore provisoires vs adultes  
6. API OVH HMAC à recréer sous **une** application  
7. Token Doppler dédié serveur vs Cursor vs Replit  
8. `KEY_API_STRIPE_ACTION` absent de GitHub Actions (à confirmer côté repo secrets)

---

## 8. Avancement

| Couche | Cette passe |
|--------|-------------|
| Vérification secrets Cursor | **100 %** (noms + APIs, 0 valeur affichée) |
| SSH + deploy OVH branche | **100 %** (live = cette branche) |
| Stripe JobPayment réel test-mode | **100 %** local + OVH |
| Alignement `KEY_API_STRIPE` | **100 %** |
| API OVH consumer/app | **0 %** (signature invalide) |
| Token Doppler dédié par plateforme | **à faire par l’utilisateur** |
| Protocole ARTCB global | **~97 %** (inchangé hors infra) |

**Cette passe infra : ~95 %.** Reste : HMAC OVH + tokens séparés + secrets GHA.

---

## 9. Compare / PR

GitHub refuse la PR automatique (`must be a collaborator`).

https://github.com/vgactech/artcb/compare/main...cursor/ovh-deploy-stripe-secrets-475d
