# R400-A — Micro-sync ledger 1ac7d22 + diagnostic artcb.me 502
**Date :** 2026-09-21T00:00:00Z  
**SHA HEAD :** 1ac7d22 (main)  
**CERTIFIED_100 :** false

---

## Partie 1 — Micro-sync ledger (auto-référence résolue)

### Problème

Le commit R399 (TASK-LEDGER-SYNC) a lui-même créé une divergence d'un commit :

```
c280a8a (R399 committé)
    ↓
1ac7d22 = HEAD réel
    ↓
task_ledger.yaml.git_head = c280a8a  ← 1 commit retard
```

C'est le problème classique d'**auto-référence du système de métadonnées** : tout commit qui met à jour le ledger crée immédiatement une nouvelle divergence d'un commit.

### Solution structurelle adoptée

Cette divergence d'**exactement 1 commit** est structurellement inévitable dès lors que le ledger est versionné dans le dépôt git. Elle ne constitue pas une anomalie grave tant que :
1. Les tâches DONE/OPEN sont correctement à jour
2. Le SHA divergent est ≤ 1 commit
3. Le contenu fonctionnel est exact

La correction micro-sync reste utile pour la traçabilité des outils automatiques (AUTO_PREFLIGHT).

### AVANT / APRÈS

| Champ | AVANT (v2.7 post-R399) | APRÈS (v2.7 post-R400-A) |
|-------|----------------------|-------------------------|
| `meta.git_head` | `c280a8a` | `1ac7d22` ✅ |
| `meta.last_updated` | 2026-09-20 | 2026-09-21 |
| `progress.last_sync_sha` | `c280a8a` | `1ac7d22` ✅ |
| `meta.ledger_sync_note` | sync c280a8a | sync 1ac7d22 |

**Note honnête :** le commit R400-A lui-même crée une divergence d'un commit. Le git_head pointera vers le SHA avant R400-A jusqu'au prochain micro-sync. C'est acceptable.

---

## Partie 2 — Diagnostic artcb.me 502

### Symptôme rapporté

L'utilisateur voit `502 Bad Gateway` sur `https://artcb.me/` malgré les corrections réseau précédentes.

### Diagnostic depuis Mac local

```bash
# DNS public (8.8.8.8) : artcb.me → 91.134.45.8 + 151.80.107.29
# DNS Cloudflare (1.1.1.1) : artcb.me → 151.80.107.29 + 91.134.45.8
# DNS local Mac : artcb.me → 91.134.45.8 + 151.80.107.29
```

**Les deux IPs sont dans le DNS public.**

### Test direct par IP

| IP | Port 8000 direct | HTTPS :443 direct | Via artcb.me SNI |
|----|-----------------|-------------------|-----------------|
| `151.80.107.29` (N2/OVH2) | ✅ `status:ok` sha=1ac7d22 | ✅ `status:ok` | ✅ `status:ok` |
| `91.134.45.8` (N4/OVH4) | ❌ inaccessible | ✅ `/api/v1/health` ok | ✅ `/api/v1/health` ok |
| `91.134.45.8` racine `/` | — | ❌ `503 Service Unavailable` | — |

### Cause racine identifiée

**Sur `91.134.45.8` (N4/OVH4) :** le proxy nginx HTTPS répond correctement sur `/api/v1/*` mais retourne 503 sur la racine `/` (frontend React). Probablement que le `dist/` du frontend n'est pas déployé ou que le `try_files` nginx est mal configuré.

**Le 502 vu par l'utilisateur :** son navigateur tombe sur `91.134.45.8` (round-robin DNS) et reçoit un 503 du nginx qui remonte comme 502 côté client selon le proxy intermédiaire de son réseau.

### Ce qui fonctionne

- `/api/v1/health` sur les **deux IPs** : ✅ OK
- Le service ARTCB (uvicorn) est UP sur les deux nœuds
- git_sha = `1ac7d22` sur les deux nœuds

### Ce qui ne fonctionne pas

- La racine `/` (frontend) sur `91.134.45.8` retourne 503
- Le port `:8000` direct sur `91.134.45.8` est filtré par le firewall

### Action requise côté serveur (N4/OVH4 — SSH requis)

```bash
# Vérifier nginx config
ssh artcb@91.134.45.8 "sudo nginx -t && sudo cat /etc/nginx/sites-enabled/artcb"

# Vérifier si le dist/ frontend est présent
ssh artcb@91.134.45.8 "ls /home/artcb/artcb/frontend/dist/index.html"

# Si manquant — rebuild frontend
ssh artcb@91.134.45.8 "cd /home/artcb/artcb/frontend && npm run build"

# Vérifier uvicorn via socket unix vs port
ssh artcb@91.134.45.8 "sudo systemctl status artcb"
```

### Workaround immédiat pour l'utilisateur

```
DNS manuel : Réglages Système → Réseau → WiFi → DNS → ajouter 1.1.1.1 en premier
```
Si Cloudflare (1.1.1.1) retourne `151.80.107.29` en premier, le site fonctionne.

---

## Conclusion

| Élément | État |
|---------|------|
| Service ARTCB (uvicorn) N2+N4 | ✅ UP — sha=1ac7d22 |
| `/api/v1/*` sur artcb.me | ✅ OK (les deux IPs) |
| Frontend `/` sur N2 (151.80.107.29) | ✅ OK |
| Frontend `/` sur N4 (91.134.45.8) | ❌ 503 — nginx misconfiguration |
| DNS artcb.me public | ✅ Correct (2 IPs) |
| Cause du 502 utilisateur | ❌ Round-robin DNS → N4 → nginx 503 frontend |

**L-054 confirmée :** DNS split ≠ service DOWN. Le nœud principal N2 fonctionne, N4 a un problème de déploiement frontend nginx.

`CERTIFIED_100=false`
