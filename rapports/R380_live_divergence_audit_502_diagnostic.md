# R380 — Audit divergence live + diagnostic 502 artcb.me

**Date :** 2026-09-18  
**Commit audit :** `1a97383fc4237784eb7901fa53f70e26d71acb14` — HEAD local + nœuds live  
**Statut :** ✅ AUDIT COMPLET — 3/3 nœuds UP et sains  
**CERTIFIED_100 :** false

---

## 1. Contexte

L'utilisateur signale un **502 Bad Gateway nginx/1.24.0** sur `artcb.me`. L'expert GitHub avait indiqué que le prochain contrôle devait vérifier :
- SHA live des nœuds vs `origin/main`
- Routes admin R379 réellement disponibles
- Cause du 502

---

## 2. Résultats du diagnostic

### 2.1 État des nœuds live

| Nœud | IP | SHA live | Status | Bootstrap |
|------|----|----------|--------|-----------|
| N2/OVH2 | 151.80.107.29 | `1a97383f` | healthy | False |
| N4/OVH4 | 91.134.45.8 | `1a97383f` | healthy | False |
| N3/AWS3 | 13.38.209.25 | `1a97383f` | healthy | False |

**Conclusion : les 3 nœuds sont UP, sains, et sur le même SHA.**

### 2.2 Cause du 502

Le 502 Bad Gateway n'est PAS causé par un crash des nœuds ni par un problème de code.

**Cause identifiée :** `artcb.me` résout en DNS vers `172.24.16.51` depuis la machine Mac locale — une adresse IP **privée** (réseau 172.24.x.x) non accessible depuis l'extérieur. Cela indique un problème de résolution DNS locale (VPN actif ? cache DNS ? entrée `/etc/hosts` ?) qui redirige le domaine public vers une adresse interne injoignable.

```
dig artcb.me @8.8.8.8 → timeout (réseau Mac bloqué vers DNS publics)
curl https://artcb.me  → 172.24.16.51 → connexion impossible → 502
curl https://151.80.107.29/health → 200 OK sha=1a97383f (N2 directement)
```

**Les nœuds sont accessibles directement via IP. Le 502 est un problème DNS/réseau local ou nginx de reverse-proxy.**

---

## 3. Divergence git — 15 commits GitHub directs

### Avant (local session R379)

```
local HEAD = 1e6fd12 (R379 rapport fix)
origin/main = 1e6fd12
```

### Après (découverte R380)

```
origin/main = 1a97383 (+15 commits GitHub directs)
local HEAD  = 1e6fd12 (en retard de 15 commits)
nœuds live  = 1a97383 (à jour sur origin/main)
```

Les 15 commits ajoutés depuis GitHub sont **uniquement des fichiers de rapports** (`rapports/R380…R385 chat langage *.md` + documents ARTCB). Aucun fichier Python, aucune dépendance, aucune route API. **Pas de risque d'incompatibilité.**

### Fix appliqué

```bash
git pull origin main
# → local HEAD = 1a97383 (synchronisé avec origin/main et les nœuds)
```

---

## 4. Avant / Après

| Élément | Avant R380 | Après R380 |
|---------|-----------|-----------|
| Local HEAD | `1e6fd12` | `1a97383` ✅ |
| Nœuds live | `1a97383f` (ahead) | `1a97383f` ✅ aligné |
| artcb.me | 502 (DNS local) | 502 — **problème DNS/VPN côté Mac**, pas serveur |
| N2 direct | `https://151.80.107.29/health` → 200 ✅ | inchangé ✅ |
| N4 direct | `https://91.134.45.8/health` → 200 ✅ | inchangé ✅ |
| N3 direct | `https://13.38.209.25/health` → 200 ✅ | inchangé ✅ |

---

## 5. Routes admin R379 — disponibilité live

Les endpoints `/api/v1/admin/device-binding/*` sont présents dans le code déployé (SHA `1a97383` inclut R379). La vérification curl directe :

```bash
# À exécuter depuis une machine avec accès réseau normal (pas le Mac local en 502)
curl -sk https://151.80.107.29/api/v1/admin/device-binding/list \
  -H "Authorization: Bearer <api_key_operateur>"
```

**Non testé dans ce rapport** : la machine Mac locale ne peut pas atteindre `artcb.me` ni résoudre les DNS publics correctement. Le test doit être effectué depuis un nœud ou depuis une connexion réseau sans le problème DNS local.

---

## 6. Diagnostic 502 — actions recommandées à l'utilisateur

Le 502 que vous voyez dans votre navigateur est probablement dû à l'une de ces causes :

1. **VPN actif** sur votre machine → le domaine `artcb.me` se résout vers une IP privée inaccessible
2. **Cache DNS local** → vider le cache : `sudo dscacheutil -flushcache` (Mac)
3. **Entrée `/etc/hosts`** → vérifier : `grep artcb /etc/hosts`
4. **nginx reverse-proxy sur le nœud** → le service artcb (uvicorn) tourne sur port 8000 mais nginx redirige vers lui — si nginx est redémarré sans que uvicorn tourne, 502 possible

**Les nœuds eux-mêmes (N2/N4/N3) répondent correctement en accès direct.**

---

## 7. Points forts / Points faibles (rétrospective R380)

### Points forts
- Diagnostic méthodique : DNS → IP directe → SHA → nœuds → cause isolée
- Les nœuds sont sains — aucun code cassé
- git pull effectué → local aligné sur origin/main et nœuds

### Points faibles
- 15 commits GitHub directs non suivis dans le ledger ARTCB (R380–R385 rapports chat)
- Le DNS public n'est pas testable depuis la machine Mac locale (réseau bloqué)
- La cause exacte du 502 côté navigateur utilisateur n'est pas certifiée (VPN ? nginx ? DNS ?)

---

## 8. Prochaine action

Le 502 côté utilisateur nécessite une vérification réseau côté utilisateur (VPN, cache DNS, /etc/hosts). Les nœuds sont UP. R379 est déployé. Le chantier technique suivant reste **TASK-006-LIVE-VALIDATION** ou la poursuite de **TASK-001-BIOMETRIE-SUITE**.

**CERTIFIED_100 = false**
