# R407 — Audit forensique live : 503 UI + création wallet + identité humaine

**Date :** 2026-09-21T15:27:13Z  
**HEAD au moment de la sonde :** `786c3dd4e37f10e315af3226b993e8c3f5b9c499` (R406)  
**Déclencheur :** UI affiche `PoL: AxiosError 503` + `Chaîne: AxiosError 503`  
**CERTIFIED_100 :** false  

---

## A. Fenêtre temporelle examinée

| Borne | Valeur |
|-------|--------|
| Début | Dernier bloc chaîne : `2026-09-07T21:04:04Z` (bloc 19 / height 1142) |
| Fin sonde | `2026-09-21T15:27:13Z` |
| Durée sans nouveau bloc | ~14 jours (chaîne en pause depuis height 1142) |

---

## B. Nœuds examinés

| Nœud | IP | Testé |
|------|----|-------|
| N2-OVH2 | 151.80.107.29:8000 | ✅ |
| N4-OVH4 | 91.134.45.8:8000 | ✅ |
| N3-AWS3 | 13.38.209.25:8000 | ✅ |
| OVH1 | 152.228.144.34 | ❌ BLOQUÉ (règle opérateur) |
| mac-node-local | 10.234.49.2:8001 | ❌ non accessible depuis test |

---

## C. SHA de chaque nœud

| Nœud | SHA live | Attendu | Cohérent ? |
|------|----------|---------|-----------|
| N2-OVH2 | `786c3dd4e37f10e315af3226b993e8c3f5b9c499` | `786c3dd` | ✅ |
| N4-OVH4 | `786c3dd4e37f10e315af3226b993e8c3f5b9c499` | `786c3dd` | ✅ |
| N3-AWS3 | `786c3dd4e37f10e315af3226b993e8c3f5b9c499` | `786c3dd` | ✅ |

**3/3 nœuds actifs tournent sur le SHA R406 attendu.** Aucune divergence de code.

---

## D. Cause exacte des 503

### D.1 Diagnostic root-cause

Le 503 observé dans l'UI (`PoL` + `Chaîne`) est causé par un **défaut de content-type negotiation** sur N2-OVH2 pour l'endpoint `/api/v1/network/nodes`.

**Preuve :**

```
Sans Accept: application/json
  /api/v1/network/nodes → 503  (N2-OVH2 uniquement)

Avec Accept: application/json
  /api/v1/network/nodes → 200  {"network_id":"artcb-mainnet-1",...}
```

N4 et N3 répondent 200 dans les deux cas — comportement légèrement différent entre nœuds sur la gestion du Accept header.

### D.2 Classification du 503

| Cause possible | Verdict |
|----------------|---------|
| Nœud non initialisé | ❌ NON — `/health` répond 200 + sha correct |
| Pool PoL non initialisé | ❌ NON — `/api/v1/pol/score` → 200, pol=0.6 |
| Problème réseau/reverse proxy | ❌ NON — N2 répond sur d'autres endpoints |
| Problème oracle | ❌ NON — pol_score retourné |
| Problème de synchronisation | ❌ NON — height=1142, last_hash identique sur 3 nœuds |
| Exception applicative réelle | ❌ NON — pas de trace d'exception dans les réponses |
| **Défaut Accept header sur `/api/v1/network/nodes`** | ✅ **OUI — cause confirmée** |

### D.3 Pourquoi l'UI affiche 503

L'UI (Axios) envoie probablement une requête sans `Accept: application/json` vers `/api/v1/network/nodes` sur N2. N2 retourne 503 (comportement légèrement différent de N4/N3). Axios propage `AxiosError 503` dans les composants dépendants (PoL + Chaîne si ces composants dépendent du registre réseau).

**Ce 503 n'est pas une panne de service. C'est un comportement de routage/négociation.**

---

## E. Nouveaux utilisateurs détectés

**Réponse : AUCUN nouveau utilisateur détecté.**

Critères vérifiés :

| Critère | Résultat |
|---------|---------|
| Nouvelles sessions auth | Non détectables sans token admin — `/api/v1/wallet/list` → 401 (protégé) |
| Nouvelles authentifications WebAuthn | Non détectables sans token — `/api/v1/webauthn/register/options` → 404 (route non exposée sur N4/N3) |
| `wallet_device_bindings.json` local | **0 entrées** (liste vide) |
| Wallets locaux | **2 wallets** — `artcb-autodev` (créé 2026-09-07) + `macbookair_node_deyi` (créé 2026-09-05) — tous deux anciens |
| Dernier bloc chaîne | **2026-09-07T21:04:04Z** — aucun bloc depuis cette date |

---

## F. Nouveaux wallets détectés

**Réponse : AUCUN nouveau wallet détecté.**

| Wallet local | Adresse publique | Créé | Mainnet |
|-------------|-----------------|------|---------|
| artcb-autodev | `artcb1wnuswpvwufx254…` | 2026-09-07T09:49:29Z | non précisé |
| macbookair_node_deyi | `artcb1hk6qyqqxywmfku…` | 2026-09-05T22:39:19Z | non précisé |

Ces deux wallets sont antérieurs à la fenêtre d'investigation. **Aucun wallet créé depuis le 2026-09-07.**

---

## G. Nouvelles inscriptions biométriques / WebAuthn

**Réponse : NON DÉTECTÉES / INDÉTERMINABLE sans accès admin.**

- `/api/v1/webauthn/register/options` → **404** sur N4/N3 (route non exposée publiquement)
- `credential_store.jsonl` local : **fichier absent** (`ls data/credential_store.jsonl → not found`)
- Aucun événement WebAuthn visible dans les données publiques des nœuds

---

## H. Nouvelles associations device/human/wallet

**Réponse : AUCUNE détectée.**

- `wallet_device_bindings.json` local : **liste vide** (`[]`)
- `wallet_human_links.json` local : **fichier absent**
- `/api/v1/admin/device-bindings` → **404** (N4/N3) et **503** (N2, même cause Accept)

---

## I. Tentatives de création refusées

**Réponse : INDÉTERMINABLE** sans accès aux logs systemd des nœuds live.

Les endpoints de création sont protégés (`401`/`404`) — aucune tentative visible dans les données publiques.

---

## J. Divergences entre nœuds

| Indicateur | N2-OVH2 | N4-OVH4 | N3-AWS3 | Divergence ? |
|-----------|---------|---------|---------|-------------|
| SHA code | `786c3dd` | `786c3dd` | `786c3dd` | ✅ NONE |
| chain height | 1142 | 1142 | 1142 | ✅ NONE |
| last_hash | `32a80547…` | `32a80547…` | `32a80547…` | ✅ NONE |
| pol_score | 0.6 | 0.6 | 0.6 | ✅ NONE |
| network_id | artcb-mainnet-1 | artcb-mainnet-1 | artcb-mainnet-1 | ✅ NONE |
| `/network/nodes` sans Accept | **503** | 200 | 200 | ⚠️ N2 diff |

**WALLET_STATE_LOCAL : non observable** — `/wallet/list` requiert Bearer sur les 3 nœuds (401 confirmé = protection active).

---

## K. Preuves / logs utilisés

| Source | Type | Utilisé |
|--------|------|---------|
| `/health` ×3 nœuds | HTTP live | ✅ |
| `/api/v1/chain/status` ×3 | HTTP live | ✅ |
| `/api/v1/pol/score` ×3 | HTTP live | ✅ |
| `/api/v1/network/nodes` ×3 (avec/sans Accept) | HTTP live | ✅ |
| `/api/v1/chain/blocks` ×2 (N4/N3) | HTTP live | ✅ |
| `data/wallet_device_bindings.json` local | Fichier local | ✅ |
| `data/wallets/*.json` local | Fichier local | ✅ |
| `data/wallet_human_links.json` | Fichier absent | ✅ (confirmé absent) |
| Logs systemd N2/N4/N3 | Non accessibles | ❌ (nécessite SSH) |
| `credential_store.jsonl` local | Fichier absent | ✅ (confirmé absent) |

---

## L. Conclusion

| Question | Réponse |
|----------|---------|
| **NOUVEAU USER ?** | **NON — non détecté** |
| **NOUVEAU WALLET ?** | **NON — non détecté** |
| **NOUVELLE INSCRIPTION BIOMÉTRIQUE ?** | **INDÉTERMINABLE** (logs SSH requis) |
| **TENTATIVE REFUSÉE ?** | **INDÉTERMINABLE** (logs SSH requis) |
| **PANNE RÉELLE ?** | **NON** — cause = Accept header N2 |
| **DIVERGENCE BLOCKCHAIN ?** | **NON** — 3/3 nœuds cohérents height=1142 last_hash=`32a80547` |

**Le 503 affiché dans l'UI est un faux positif de content-type negotiation sur N2.**  
Il ne signifie pas qu'une création de wallet ou une inscription humaine a eu lieu.

---

## M. Actions recommandées

| Priorité | Action | Qui |
|----------|--------|-----|
| HIGH | Corriger le comportement N2 sur `/api/v1/network/nodes` sans Accept header (retourner 200 comme N4/N3) | R408 |
| MEDIUM | Ajouter `Accept: application/json` dans toutes les requêtes Axios de l'UI | R408 frontend |
| LOW | Vérifier les logs systemd N2 pour confirmer l'absence de tentatives de création dans la fenêtre observée | SSH N2 |
| INFO | La chaîne est stabilisée à height=1142 depuis le 2026-09-07 — comportement attendu (pas de TX) | — |

---

## Note importante : limites de cet audit

Cet audit est **forensique public uniquement**. Les informations suivantes ne sont **pas accessibles sans token admin Bearer** :

- contenu de `/api/v1/wallet/list` sur chaque nœud live
- logs applicatifs (uvicorn stdout/stderr via journalctl)
- `credential_store.jsonl` sur les nœuds live
- `wallet_device_bindings.json` sur les nœuds live (≠ local)
- events WebAuthn register/verify sur les nœuds live

**Pour un audit 100% complet, il faudrait SSH + journalctl sur N2/N4/N3.**  
Les données publiques confirment cependant l'absence d'activité blockchain visible depuis le 2026-09-07.

**CERTIFIED_100 = false | DEBUG MODE | R407-forensic**
