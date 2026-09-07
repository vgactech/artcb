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

## 4. Live (à remplir après follow-main ×4 + replica/run)

SHA `origin/main` / `/health` : *(mesuré)*  
OVH1 height / tip : *(mesuré)*  
OVH2 / AWS3 / OVH4 avant : *(mesuré)*  
OVH2 / AWS3 / OVH4 après : *(mesuré)*  
Flux summary (`GET /p2p/flux`) : *(mesuré)*  
Graphes présents sur les 3 répliques : *(mesuré)*  
idx 0–4 inchangés (`b8a7d5ef` … `27350024`) : *(mesuré)*

---

## 5. Interdit

Wipe `blocks.jsonl`. `install.sh`. Genesis. `init-node`. Rescue. Afficher le token. Mélanger les Doppler. Poster du private vers un pair hors allowlist.
