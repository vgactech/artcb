# Rapport 251 — Les 1074 sur tous les nœuds + flux réel

**Date :** 2026-09-07  
**GO :** le public doit propager. Les 1074 (et ce qui manquait : graphes, index, KCG, métriques de flux) doivent être sur les 4 nœuds officiels.  
**Pas de wipe. Pas de D-0xx. GO-E produce off.**  
**Contact :** `official@artcb.space`

Les hauteurs, hashes, octets et RTT du §4 sont mesurés **après** exécution. Rien n’est inventé.

---

## 0. Pourquoi les 1074 n’étaient pas sur OVH2 / AWS3 / OVH4

Trois faits empilés — pas un mystère réseau.

1. **L’ingest 1065 n’a jamais quitté OVH1.**  
   `POST /api/v1/ai/ingest-batch` × 1065 sur `152.228.144.34` seulement. Aucun `POST /p2p/blocks/receive`, aucun replica, aucun `/p2p/sync`.  
   **Il n’existe aucun log de flux inter-nœuds pour cet envoi** : il n’y a pas eu d’envoi. `GET /p2p/flux` est vide jusqu’à la première réplique réelle.

2. **La règle 222 archivait tout public qui n’était pas `DOMAIN_COMMITMENT` / `ORG_CONTROL_TRANSFER`.**  
   Un bloc public qui prolongeait le tip (`index` + `prev_hash` + hash) allait en `archive_only`. Ça contredit l’objectif du `visibility=public`.

3. **Même après correction de (2), le pull public seul ne peut pas reconstruire cette chaîne.**  
   717 public / 357 private, intercalés. Le `prev_hash` d’un public pointe souvent sur un privé. `GET /p2p/blocks/public` n’envoie que le public. Le dernier bloc (1073) est **private** : le tip lui-même n’est pas public.  
   Les 4 nœuds officiels ne sont pas des pairs anonymes. Ils doivent avoir **le livre entier** + `data/graphs/` + `data/memory/repo_index.jsonl` + `data/kcg/`, sinon `/ai/ingest/file` casse.

---

## 1. Ce qui a été développé

| Chemin | Qui | Quoi |
|---|---|---|
| Anonyme `/p2p/blocks/*` | n’importe quel pair | **public qui prolonge le tip → append**. Forks rejetés. Private rejeté. |
| Officiel `/p2p/replica/*` | IPv4 des 4 compute seulement | **livre complet** (toute visibilité), par chunks de 20, ML-KEM + AES-GCM |
| Fichiers replica | idem | graphes IR, index ingest, KCG |
| `GET /p2p/flux` | public | JSONL `data/p2p/flux.jsonl` : pair, direction, chunk, octets, encrypt_ms, http_ms, rtt_ms, height, ok/error |
| `POST /p2p/replica/run` | bearer opérateur | OVH1 pousse vers les 3 autres |

Allowlist replica : `152.228.144.34`, `151.80.107.29`, `51.44.222.232`, `91.134.45.8` + loopback (tests / nginx). `X-Forwarded-For` n’est lu que si le TCP peer est loopback. Un pair anonyme qui POST du private reçoit 403.

---

## 2. Tests

- `tests/test_e2e222_tip_resilience.py` — `test_k` : un public quelconque qui prolonge le tip **append**
- `tests/test_e2e251_public_propagate.py` — allowlist, public vs private anonyme, replica mixed chain, flux, fichiers, HTTP loopback

---

## 3. Ce que l’ingest 1065 n’a pas mesuré (honnête)

| Métrique | Ingest 1065 |
|---|---|
| Octets fil OVH1 → OVH2/AWS3/OVH4 | **0** (pas d’envoi) |
| RTT inter-nœud | **absent** |
| encrypt_ms / http_ms | **absent** |
| Propagation height 5 → 1074 | **jamais tentée** |

Le flux réel est celui du `replica/run` §4.

---

## 4. Live (mesuré 2026-09-07T21:39:25Z → 21:54:25Z)

`origin/main` = `/health` ×4 = **`c32aee46c5a9f79375d17e810a75b2ac3225bb16`**.  
follow-main keep-book ×4. Livre OVH1 resté **1074** lignes. Pas de wipe.

| Nœud | Avant | Après | tip après | `chain_valid` | graphes | `repo_index` | KCG |
|---|---|---|---|---|---|---|---|
| OVH1 `152.228.144.34` | 1074 / `3d1231cd…` | **1074** / `3d1231cde101b70f77f852f3b7db698a0b8d8558fa6b747e51189450659c3acf` | idem | true | 1073 | 3539 | 2 |
| OVH2 `151.80.107.29` | **5** / `27350024…` | **1074** / même tip | même | true | 1082 (9 anciens + 1073) | 3539 | 2 |
| AWS3 `51.44.222.232` | **5** / `27350024…` | **1074** / même tip | même | true | 1073 | 3539 | 2 |
| OVH4 `91.134.45.8` | **5** / `27350024…` | **1074** / même tip | même | true | 1073 | 3539 | 2 |

idx 0–4 identiques sur les 4 disques : `b8a7d5ef…` `5c952df6…` `93eab711…` `5e4dbb40…` `27350024…`.  
Visibilité : **717 public / 357 private**. Dernier bloc 1073 = **private** (c’est pour ça que le P2P public seul ne pouvait pas porter le tip).

`GET /ai/ingest/catalog` sur OVH2 / AWS3 / OVH4 : **3539** (reread après replica fichiers).

### Flux réel — `GET /p2p/flux` OVH1 (570 lignes, **0 erreur**)

Ingest 1065 : **0** octet inter-nœud (pas d’envoi). Ce flux est **celui-ci**.

Blocs (1069 nouveaux / pair, index 5→1073, chunks de 20 + 1 `nothing_to_send`) :

| Pair | chunks ok | octets fil | encrypt_ms moy | http_ms moy | rtt_ms min / moy / max |
|---|---|---|---|---|---|
| OVH2 `151.80.107.29` | 55 / 0 err | 16 623 668 | 49.25 | 2674.52 | 414.53 / **2723.77** / 5311.61 |
| AWS3 `51.44.222.232` | 55 / 0 err | 16 623 668 | 44.93 | 1691.19 | 293.20 / **1736.12** / 4738.01 |
| OVH4 `91.134.45.8` | 55 / 0 err | 16 623 668 | 49.21 | 1744.62 | 317.57 / **1793.83** / 3413.44 |

Fichiers (1076 objets / pair = 1073 graphes + index + 2 KCG) :

| Pair | chunks ok | octets fil | encrypt_ms moy | http_ms moy | rtt_ms min / moy / max |
|---|---|---|---|---|---|
| OVH2 | 135 / 0 err | 84 263 273 | 43.85 | 143.19 | 147.65 / **187.04** / 295.75 |
| AWS3 | 135 / 0 err | 84 263 273 | 43.98 | 168.17 | 173.12 / **212.15** / 307.54 |
| OVH4 | 135 / 0 err | 84 263 273 | 50.52 | 153.19 | 157.22 / **203.71** / 323.29 |

Total fil mesuré : **302 660 823** octets. Blocs ~5 min 40 s (21:39:25Z–21:45:05Z). Fichiers ensuite (dernier chunk 21:54:25Z). nginx `:8443` a renvoyé 504 à 60 s — le handler uvicorn a **continué**. Déclencher via `POST /p2p/replica/run` (bearer) depuis OVH1, source IP officielle vers `:8000`.

Anonyme `GET /p2p/replica/blocks` depuis l’agent cloud : **403** `official_replica_peers_only`. `private_never_synced` reste true pour le P2P public.

---

## 5. Interdit

Wipe `blocks.jsonl`. `install.sh`. Genesis. `init-node`. Rescue. Afficher le token. Mélanger les Doppler. Poster du private vers un pair hors allowlist.
