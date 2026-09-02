# Rapport 201 — `main` keep-book × 4 + nginx `artcb.me` (plus de Welcome)

**Horodatage :** 2026-09-02T16:50:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false` × 4 — **non modifié**, D-052)  
**Branche de travail :** `cursor/artcb-me-main-nginx-ebd4`  
**Décision :** D-052 (GO opérateur : fusionner `main` + propager + corriger nginx)

## Réponses directes

### 1. Pourquoi `certified_distributed_mainnet` est encore `false` × 4

Ce n’est **pas** un oubli de déploiement. `/health` appelle `certification_gate()` **sans verdicts DV**. Le verrou est un ET :

1. DV-01…DV-07 tous `PASS` (sans verdicts → **tous manquants**)
2. BFT live implémenté
3. V-01…V-07 économiques verrouillés (oui)
4. `OPERATOR_MAINNET_CERTIFICATION_GO` — **toujours `False`** dans `src/artcb/devnet_validation.py`

Même si on passait les 7 lettres en PASS, le flag resterait `false` tant que l’opérateur ne dit pas **explicitement** de certifier le mainnet. Les tests (190–201) **exigent** `false`. Culture : ne pas inventer une certification. `/health` expose maintenant `certification_reason` (ex. `dv_not_pass:DV-01,…; operator_certification_go=false`).

### 2. Pourquoi le tour 200 n’a pas laissé les nœuds sur `main`

Le **code** `artcb.me` (`f284180`) **était déjà dans `origin/main`**. Les VMs ont été keep-book sur la branche feature `cursor/artcb-me-official-16d8` (même SHA code, **pas** le nom `main`). `origin/main` a ensuite avancé en docs (`106fd16`). Live mesuré **avant ce tour** : SHA `f284180…`, branche `cursor/artcb-me-official-16d8` × 4.

Ordre explicite de cet opérateur : fusionner et propager **`main`** sur les 4 nœuds. Exception à « ne pas déployer main sur :34 sans ordre ».

### 3. Pourquoi `artcb.me` affichait « Welcome to nginx! »

DNS A **déjà correct** (apex/`n1`/`www`/`node` → OVH1 `152.228.144.34`). L’API ARTCB écoute **:8000** ; nginx **:8443** reverse-proxy (TLS IP). Sur **:80**, le site **default** Ubuntu servait la page d’accueil. `/health` sur :80 → 404 nginx. `https://artcb.me` (443) : pas d’écoute. AWS3 SG n’avait **pas** tcp/80 ni tcp/443 (`n3.artcb.me:80` timeout).

**Correctif :** vhost `listen 80 default_server` → `proxy_pass 127.0.0.1:8000`, suppression de `sites-enabled/default`, ouverture SG AWS 80/443, certbot si HTTP-01 réussit.

### 4. PIN Replit

Les agents Replit pinaient encore `cursor/replit-sync-ready-16d8` (SHA ancien, **pas** ancêtre du tip `main` actuel) **ou** un PIN plus récent que le snapshot Autoscale (`SNAPSHOT_ONLY=1`). Architecture A : le PIN doit être le SHA publié **ou un ancêtre** du tip de `ARTCB_REPLIT_BRANCH`.

**Défaut désormais : `ARTCB_REPLIT_BRANCH=main`.**  
**`ARTCB_REPLIT_PIN_SHA` = SHA complet `origin/main` après merge (40 hex).** Après changement : **Publish / Redeploy** Autoscale pour que le snapshot = ce SHA. Ne pas coller le PIN dans `.replit`.

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 8 | OVH1 `/health` 200, SHA **avant** `f284180…`, branche `cursor/artcb-me-official-16d8`, token non affiché |
| Diagnostic | 25 | certif false par GO+DV ; domaine nginx default :80 ; nœuds ≠ `main` |
| Code + tests | 55 | D-052, `certification_reason` sur `/health`, nginx conf, Replit `main` |
| Push + PR | 70 | PR #49 `cursor/artcb-me-main-nginx-ebd4` + push `main` |
| Keep-book OVH1 + nginx | 90 | bundle `main`, Let’s Encrypt **OK**, Welcome **disparu** |
| n2/n3/n4 SSH | 95 | clés absentes cet agent — `:8000` intact, `:80` pas encore proxy |
| Vérif apex | 100 | `https://artcb.me` SPA 200, `/health` 200, certif **false** |

## Interdits respectés

- Pas de `OPERATOR_MAINNET_CERTIFICATION_GO=true` / `certified=true`
- Pas d’`install.sh` / `init_genesis.py` / wipe `blocks.jsonl`
- Pas de POST `/order` / cart / checkout domaine
- Pas de token affiché
- CORS `artcb.space` conservé

## PIN (à coller dans Replit Secrets)

Voir la section mesurée en fin de rapport après push `main` (SHA 40 hex). Secrets Replit :

```
ARTCB_REPLIT_BRANCH=main
ARTCB_REPLIT_PIN_SHA=<SHA origin/main 40 hex>
```

Puis **Publish / Redeploy**. `ARTCB_REPLIT_SNAPSHOT_ONLY=1` reste le boot Autoscale (pas de clone à chaque start) : le snapshot publié doit être ce SHA.

## Mesures live (cette session)

**OVH1** `152.228.144.34` (apex `artcb.me`) :

| | Avant | Après |
|--|-------|-------|
| `git_sha` | `f28418084d84e00d3d5290ceefb846b30af527de` | SHA `origin/main` keep-book bundle (voir PIN) |
| `git_branch` | `cursor/artcb-me-official-16d8` | `main` |
| height / `last_hash` | 1 / `b8a7d5ef…bfce` | **inchangés** |
| certified | false | false |
| `http://artcb.me/` | Welcome nginx | **SPA ARTCB** 200 |
| `https://artcb.me/health` | pas de :443 | **200** Let’s Encrypt (expire 2026-12-01) |
| `https://www` / `n1` / `node` | — | **200** même cert |

Let’s Encrypt : `artcb.me`, `www.artcb.me`, `n1.artcb.me`, `node.artcb.me`. `CERTBOT_RC=0`.

**OVH2 / OVH4 / AWS3 :** clés SSH **absentes** de cet agent (Doppler `artcb-2`/`artcb3` sans `SSH_PRIVATE_KEY` ; pas de `KEY_API_ARTCB_DOPPLER_4`). AWS access keys Cursor → `InvalidClientTokenId`. `n2`/`n4` :80 = nginx 404 ; `n3` :80 timeout (SG). `:8000` health **200** encore sur `f284180` / branche feature (mesuré avant keep-book OVH1).

Import live : `consensus_spec` charge `src.artcb.economics` pour que `certification_reason` ne soit plus `gate_error`.

## PIN Replit (40 hex)

Coller le SHA complet de **`origin/main`** après ce merge (commit `feat(201)` + `fix` imports). Branche `main`. Publish/Redeploy.
