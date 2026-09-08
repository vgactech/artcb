# Rapport 258 — Solutions aux six gaps 257

**Date :** 2026-09-08  
**Contact :** `official@artcb.space`  
**Pas de wipe. Pas d’arrêt de nœud pour « tester » une partition. Pas de rewrite de `blocks.jsonl`.**

Mémoire lue avant : `GET /ai/memo/1075` = leçon 257. Live `a89eb4e`, height **1076**, tip `d71676d3…`.

Ce rapport **propose** une solution par faille, puis ce qui est **codé** (258) vs ce qui reste **non démontré en réel**.

---

## 1. ConceptID FR/EN/ES overlap 0

### Cause réelle
`ConceptID = hash(type + symbole)`. Le calcul est correct.  
L’encodeur assignait un **symbole différent par langue** : triggers FR-only, et un FACT sans objet appelait `mint_original(phrase)` → unique par texte.

Le test §30 de 247 « passait » en **forçant** `sym="V1"` à la main. Le probe live encodait vraiment FR/EN/ES → overlap 0.

### Solution
Lexique FR/EN/ES → codes ARTCB (`concept_lexicon.py`).  
`_build_symbol` prend **tous** les objets matchés (triés) : `V1` + `N1` (serveur) + `S2` (signature) = `V1N1S2` dans les trois langues.

Inconnu → mint toujours (pas de fausse convergence).

### Codé
`GET /api/v1/ir/concept-ids?q=`  
Test `test_encoder_fr_en_es_probe_overlap` sur les **phrases du probe 254**.

### Pas encore
Un lexique universel. Un embedding. Un LLM. Convergence hors table.

---

## 2. BFT / failover / partition

### Cause réelle
188 = BFT **settlement** prepare/commit (N=4, F=1, Q=3).  
L’append de bloc = plus longue chaîne publique. Réplication 251 ≠ consensus.  
On **n’arrête pas** les 4 nœuds officiels pour fabriquer une partition.

### Solution
1. **Observer** le quorum : `/consensus/liveness` ping `/health` ×4, `partitioned = reachable < Q`.  
2. `would_failover` seulement si le producteur est silencieux **et** Q tient. GO-E produce **off** — on ne vole pas la production.  
3. BFT append de bloc = autre chantier (D-0xx + GO explicite). Pas dans 258.

### Codé
`assess_liveness()` + route + tests matrice 4 up / 1 down / 2 down.

### Pas encore
Failover live, view-change, partition adversariale, BFT sur `append_block`.

---

## 3. Stockage binaire de l’historique (253)

### Cause réelle
253 : le JSONL commis est **immuable**. Réécrire 0–1075 en binaire cassse le livre.

### Solution
Sidecar `blocks.bin` (magic `ABLK`, records length-prefixed) **uniquement pour les blocs nouveaux**.  
`verify()` reste sur `blocks.jsonl`. Pas de conversion rétroactive.

Un futur bloc de transition pourra annoncer « ère binaire » sans toucher l’historique.

### Codé
`binary_log.py` branché sur `append_block` / `import_extending_block`.

### Pas encore
Lecture live via `/chain/stream?encoding=bin`. Migration des 1076 lignes. MessagePack/zstd du bloc entier.

---

## 4. GRA11 : 8 GET saturent la file TCP

### Cause réelle
Handler O(1) ≠ accept queue. 1 worker uvicorn, backlog petit, keep-alive long, plus 8 `/chain` **sans limit** qui lisent le livre.

### Solution
- uvicorn `--backlog 2048 --limit-concurrency 32 --timeout-keep-alive 2` (`start_node.sh`)  
- **Limite par défaut 256** sur `/chain` et `/chain/blocks` (`full=1` pour l’ancien comportement)  
- Explorer / export / block-sizes : plus de full verify ni `json.dumps` du livre  
- Cache bridges 20 s (voir §6)

### Codé
Les quatre points. Restart nœud requis pour les flags uvicorn.

### Pas encore
Mesure live 8-wide après follow-main. Plusieurs workers uvicorn (à calibrer vs 1 vCPU GRA11).

---

## 5. `/chain` `/export` `/explorer` `/block-sizes` sans limit = O(n)

### Solution
| Route | Avant | 258 |
|---|---|---|
| `/chain` `/chain/blocks` | tout | `limit=256`, `full=1` pour tout |
| `/export` | tout | `from_index` + `limit=256` |
| `/explorer` | `list_blocks` + `verify()` full | tip + 10 derniers |
| `/block-sizes` | `json.dumps` chaque bloc | tailles via offsets `.off` |

Chemin streaming inchangé : `/chain/stream`.

---

## 6. Bridges GRA11 ~14 s

### Cause réelle
Egress RPC publics depuis GRA11 (max des 6 pings). AWS ~0.2–0.9 s. Pas le livre.

### Solution
Cache TTL **20 s** (stale OK pour un status). Ne plus relancer 6 RPC à chaque GET du probe.

Suite possible (non codée) : RPC privés Doppler, pas de bitcoin depuis GRA11, SWR background.

---

## Tests locaux

`pytest tests/test_e2e258_gap_fixes.py tests/test_e2e257_stream_book.py tests/test_e2e254_ns_trace.py tests/test_e2e247_go_k_concept_memory.py` : **40 passed**.

---

## 7. Live après GO deploy (2026-09-08T00:35Z → 00:38Z)

Rien d’inventé. follow-main keep-book ×4 : livres restés à **1076** jusqu’au mémo.

`origin/main` = `/health` ×4 = **`5d8cef808e8a2cba7be59e39ac5531fb58483b18`**.

### ConceptID — mesuré sur OVH1 et AWS3

Phrases du probe 254/257 :

| Langue | texte | symbol | ConceptID |
|---|---|---|---|
| FR | Le serveur doit vérifier la signature. | `V1N1S2` | `Kc55d3ab3505178da` |
| EN | The server must verify the signature. | `V1N1S2` | `Kc55d3ab3505178da` |
| ES | El servidor debe verificar la firma. | `V1N1S2` | `Kc55d3ab3505178da` |

**Overlap probe = 1** (les trois IDs identiques). Plus 0.

Benchmark demandé par l’audit (`voiture` / `car` / `coche`) : **overlap 0**. EN `car` tombe encore sur le mot-clé raison FR. **Pas un PASS universel.**

### Liveness — observé, pas un test BFT

`GET /consensus/liveness` ×4 : `n=4` `q=3` `reachable=4` `partitioned=false`.  
Aucun nœud arrêté. Aucun producteur tué. **BFT / failover / partition adversariale : toujours non démontrés.**

### Routes (séquentiel, ns serveur)

| Surface | OVH1 | OVH2 | AWS3 | OVH4 |
|---|---|---|---|---|
| `/chain/status` tip | 8.4 ms | 12.8 ms | 3.6 ms | 8.9 ms |
| `/chain/stream?from=1070&limit=8` | 3.8 ms | 2.8 ms | 1.9 ms | 2.5 ms |
| `/chain` default 256 | 70.6 ms `truncated` | 54.9 ms | 22.5 ms | 34.7 ms |
| `/explorer` | 4.6 ms | 4.7 ms | 3.3 ms | 5.6 ms |
| `/block-sizes` | 19.7 ms | 18.8 ms | 14.3 ms | 21.0 ms |
| bridges 1er GET | 14.06 s | 14.06 s | 291 ms | 14.14 s |
| bridges 2e GET (cache) | **1.5 ms** | **1.8 ms** | **1.3 ms** | **1.9 ms** |

### Burst 8 × `/chain/status` parallèle

OVH1 : **8/8 OK, 0 timeout**, wall 343 ms.  
AWS3 : **8/8 OK, 0 timeout**, wall 303 ms.  
C’est le status O(1), pas un probe OpenAPI 100 routes. GRA11 n’est pas « résolu pour toute charge ».

### Mémo + KCG + replica + sidecar

`POST /ai/memo` : HTTP 200, bloc **1076** hash `b44ee5318a7f92d5ab57ba10d09c717f3d7dbc37d9eb1987fc2645ca4dec5d95` graph `ai_memo_21b7ad020b7c`.  
KCG `K_b04c41cf4ce74dec` + consult `C_b26183c85cc4f287` + use 200.

Replica depuis 127.0.0.1 OVH1 : OVH2/AWS3/OVH4 **1076→1077**, même tip `b44ee531…`, imported 1, 0 erreur.

Sur OVH1 : `blocks.jsonl` **1077** lignes (pas vidé). `blocks.bin` existe, magic **`ABLK`**, **7759** octets — sidecar des blocs **nouveaux** seulement, historique JSONL intact.

Après replica, status localhost 2.7 ms, height 1077, `chain_valid=true`.
