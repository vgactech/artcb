# Rapport 200 — `artcb.me` officiel (déjà acheté), DNS OVH4, CORS transition, keep-book × 4

**Horodatage :** 2026-09-02T16:25:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false` × 4, non modifié)  
**Branche de travail :** `cursor/artcb-me-official-16d8`  
**SHA déployé (4 nœuds) :** `f28418084d84e00d3d5290ceefb846b30af527de`  
**`origin/main` (non déployé) :** `9fab06023b69984e2651e175fdbc445403502b3e`  
**Achat domaine :** **aucun** (`order_attempted=false`). L’opérateur a déjà acheté `artcb.me`.

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **Domaine officiel** | `artcb.me` — registrar OVH, nic **xy4589-ovh** (OVH4). |
| **Transition CORS** | `artcb.space` (IONOS, rapport 197) reste dans la liste blanche le temps de la migration. |
| **Keep-book** | Checkout du SHA + `/etc/artcb/release.env` + `systemctl restart artcb`. Pas d’`install.sh`, pas d’`init_genesis.py`, pas de wipe `blocks.jsonl`. |
| **Livre** | `data/chain/blocks.jsonl` — height **1**, hash `b8a7d5ef…bfce`. |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 8 | OVH1 HTTPS 8443 HTTP **200**, SHA live **avant** `f8118ffea00b1cad5cb3396e29c923b379f6c815`, token non affiché |
| Auth OVH4 | 20 | GET `/me` **200**, nichandle **xy4589-ovh**, email public `vgac42@gmail.com` |
| GET `/domain` | 35 | `["artcb.me"]` — **déjà sur ce nic**. Pas d’autre nic à chercher. |
| Zone DNS | 55 | PUT apex + www ; POST n1 n2 n3 n4 node ; refresh **200**. **Aucun** POST `/order` / cart / checkout |
| Code + tests | 70 | `ARTCB_DOMAIN=artcb.me`, CORS `artcb.space` conservé. pytest `test_artcb_me_official` + 190/198 : **24 passed** |
| Push branche | 80 | `cursor/artcb-me-official-16d8` → GitHub |
| Keep-book × 4 | 95 | Bundle git (GitHub HTTPS refusé sur les 4 VMs). SHA unique `f284180…` |
| Vérif live | 100 | Health **200** × 4, HTTPS **200** × 4, même `last_hash`, certif **false**, DNS public résolu |

## Interdit respecté — pas d’achat

- Script `scripts/ovh4_artcb_me_dns.py` : deny-list `/order`, `/cart`, `checkout`. Un `POST /order/cart` retourne `forbidden_order_cart_checkout` **sans** appel réseau.
- Un script d’order (`ovh4_order_artcb_me.py`) présent dans le workspace (autre agent) a été **supprimé**, jamais exécuté avec `--order`.
- GET `/domain` seulement. Zone : PUT/POST `/domain/zone/artcb.me/record` + POST refresh.

## DNS mesuré (API OVH4 + résolution publique)

NS zone : `dns111.ovh.net` / `ns111.ovh.net`. TTL A = 300. Pas d’AAAA inventée.

| Nom | Type | Cible |
|-----|------|-------|
| `artcb.me` (apex) | A | `152.228.144.34` (OVH1 canonique) — PUT, ancien parking `213.186.33.5` |
| `n1.artcb.me` | A | `152.228.144.34` |
| `n2.artcb.me` | A | `151.80.107.29` |
| `n3.artcb.me` | A | `51.44.222.232` |
| `n4.artcb.me` | A | `91.134.45.8` |
| `node.artcb.me` | A | `152.228.144.34` (alias) |
| `www.artcb.me` | A | `152.228.144.34` (parking remplacé) |

Résolution `getaddrinfo` depuis l’agent : **identique** aux cibles ci-dessus (propagation déjà visible).

## Code

- `ARTCB_DOMAIN = "artcb.me"`
- `ARTCB_DOMAIN_LEGACY = "artcb.space"` → CORS `https://` et `http://` pour apex + n1…n4 + node + www
- P2P `is_official_artcb_host` accepte `.artcb.me` **et** `.artcb.space`
- Import live : `from src.artcb.config import …` (`start_node.sh` lance `uvicorn src.api.main:app` depuis la racine du clone, sans `PYTHONPATH=src`)

## Keep-book (4 nœuds)

GitHub HTTPS : `fatal: could not read Username` sur **OVH1, OVH2, AWS3, OVH4** → bundle local, même SHA.

Premier passage (sim `20260902T161736Z`) : SHA **mélangés** (`6b003f5` / `8fd3a45`) — un autre agent a écrasé `/tmp/artcb-me-200.bundle` et a retargeté le script vers `main`. **Corrigé** : branche restaurée, bundle unique `pid+SHA`. Sim canonique : `20260902T162209Z_e2e200_artcb_me_official`.

| Nœud | IP | `git_sha` | `git_branch` | health HTTP | HTTPS 8443 | height | `last_hash` | certified |
|------|-----|-----------|--------------|-------------|------------|--------|-------------|-----------|
| OVH1 | 152.228.144.34 | `f28418084d84e00d3d5290ceefb846b30af527de` | `cursor/artcb-me-official-16d8` | 200 | 200 | 1 | `b8a7d5ef…bfce` | **false** |
| OVH2 | 151.80.107.29 | idem | idem | 200 | 200 | 1 | idem | **false** |
| AWS3 | 51.44.222.232 | idem | idem | 200 | 200 | 1 | idem | **false** |
| OVH4 | 91.134.45.8 | idem | idem | 200 | 200 | 1 | idem | **false** |

`blocks.jsonl` : **1 ligne** × 4 (`wc -l` remote). `install.sh` / `init_genesis.py` / init-node : **non exécutés**.  
PQC : `ML-DSA-65`, `hybrid_and_function=verify_hybrid_and`, `high_value_hybrid_enforced=false`.  
Mutations P2P non auth : DELETE peers **401**.  
`origin/main` **n’a pas** été poussé ni déployé (règle nœud live + demande opérateur = branche 16d8).

## Tests

```
PYTHONPATH=src python3 -m pytest \
  tests/test_artcb_me_official.py tests/test_e2e198_hybrid_and_call_sites.py \
  tests/test_e2e190_mainnet_validate.py -q
```

**24 passed.** Le script DNS refuse `/order/cart` et checkout. CORS contient `https://artcb.me` **et** `https://artcb.space`.

## Interdits (rappel)

- Pas de POST `/order`, pas de cart domaine, pas de checkout
- Pas d’`install.sh` / genèse / wipe livre
- Pas de 2ᵉ VM OVH, pas de checkout bare-metal 258100013
- Pas de tokens / clés affichés
- Pas de `certified=true` / `OPERATOR_MAINNET_CERTIFICATION_GO`

## Suite opérateur (hors de cette mission)

- Let’s Encrypt sur `artcb.me` / `n1`…`n4` (HTTPS nommé, aujourd’hui IP:8443)
- Quand IONOS `artcb.space` n’est plus nécessaire : retirer `ARTCB_DOMAIN_LEGACY` du CORS
- Fusionner `cursor/artcb-me-official-16d8` dans `main` **sur ordre explicite**
