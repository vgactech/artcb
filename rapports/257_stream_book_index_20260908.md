# Rapport 257 — Index offsets + stream NDJSON + status O(1)

**Date :** 2026-09-08  
**GO :** se mettre à jour (`255`/`256`), mémoire ARTCB, traces **ns** bout-en-bout y compris le livre, exercer **toutes** les surfaces développées en réel, optimiser le **streaming**.  
**Pas de wipe. Pas de D-0xx. GO-E produce off.**  
**Contact :** `official@artcb.space`

Les chiffres du §4 sont mesurés après follow-main + probe. Rien n’est inventé.

---

## 0. Rapports distants et mémoire live

`origin/main` au départ : **`aaefa7a80622f48b4bbbe80646c07e8a608d8a5c`**.  
Live `/health` HTTP `:8000` : même SHA, `branch=main`.  
Height **1075**, tip `ce82d755af9549477f761262aeb0243d17d1972e679da0c70efe93facc8f5b48`, `last_index` **1074**, `chain_valid=true`.

`GET /ai/memo/1074` (lu **avant** reconstruction) : leçon 254, graph `ai_memo_2dca3353999d`, tags `254,trace_ns,live_probe,memory`. Texte : traces ns + probe live ; ConceptID / BFT non démontrés.

`GET /ai/context` : 1067 memos IA ; derniers = 1074 lesson, 1073/1072 ingest repo.

KCG bootstrap : 3 knowledge / 2 consults / 2 uses.

### 255

254 est une **vraie** avance (traces ns + convergence 1075) mais : GRA11 sature sous 8 GET parallèles ; `bridges/status` ~105 s ; lectures livre trop chères ; SSE intestable ; ConceptID 0 overlap ; BFT/failover/partition **non** démontrés. Réplication ≠ consensus.

### 256

**IR / index d’abord, lecture ciblée du bloc ensuite.** Jamais `GET /chain` → `_read_all_blocks()` → recherche. Chemin : authz → index/IR → KnowledgeID → BlockID → un record → preuve de hash.

---

## 1. Code

- `src/artcb/chain/book_index.py` — offsets uint64 + `.off.meta` (size/count/tip/graphs/issued). Rebuild si la taille jsonl dérive. Traces `book_rebuild` / `book_get` / `book_iter` / `book_index_append`.
- `ChainManager` : `height` / `tip` / `get_block` / `last_hash` / import / append via l’index. `chain_valid_tip()` = hash du dernier bloc.
- `GET /chain/status` O(1) (`verify_mode=tip`). Full verify = `?verify=1` ou `GET /chain/verify`.
- `GET /chain/block/{i}` → `get_block` (plus de scan).
- `GET /chain` et `/chain/blocks` : `from_index` + `limit`.
- **`GET /api/v1/chain/stream`** `application/x-ndjson` — seek + flush ligne à ligne.
- `GET /chain/search` : vecteurs → authz → `block_index_for_graph` → un `get_block`. Plus de `list_blocks()`.
- SSE `/ai/events?max_seconds=` : `height()` + `get_block(height-1)`. Probe-safe.
- Bridges `status_all` : 6 pings **parallèles**, timeout 2 s (plus 6 × 15 s séquentiels).
- Middleware HTTP : `query` tronqué + `X-ARTCB-Trace-Ns`. Wailly excerpt aussi tracé.
- Probe `scripts/artcb_live_full_probe.py` : stream + SSE court + status + bridges.
- Tests `tests/test_e2e257_stream_book.py`.

Pas de rewrite binaire de l’historique (253). Pas d’arrêt de nœud / fork adversarial (255 : hors de cette passe).

---

## 2. Tests locaux

`pytest tests/test_e2e257_stream_book.py tests/test_e2e254_ns_trace.py tests/test_e2e251_public_propagate.py` : **16 passed**.

---

## 3. Interdit toujours

Wipe `blocks.jsonl`. `install.sh`. Genesis. `init-node`. Rescue. Afficher le token. Mélanger Doppler. Inventer un PASS ConceptID ou BFT.

---

## 4. Live (mesuré 2026-09-08T00:10Z → 00:17Z)

`origin/main` = follow-main ×4 = `/health` ×4 = **`dd46b7eb2e6e77d1eb2caa67608aa3c0c7502867`**.  
Livres restés à **1075** lignes jusqu’au mémo (pas de wipe).

### Status / stream / livre — séquentiel (ns serveur `X-ARTCB-Trace-Ns`)

Avant (254, OVH1 séquentiel) : `/chain/status` **~195 ms** serveur (full list + full verify). `bridges/status` **~105.7 s**.

Après 257, même hauteur 1075, **séquentiel** :

| Surface | OVH1 srv | OVH2 srv | AWS3 srv | OVH4 srv |
|---|---|---|---|---|
| `/chain/status` tip | **8.1 ms** | 5.8 ms | 3.2 ms | 4.3 ms |
| `/chain/block/0` | 7.7 ms | 4.4 ms | 2.3 ms | 2.2 ms |
| `/chain/block/1074` | 3.3 ms | 2.4 ms | 1.6 ms | 2.0 ms |
| `/chain/stream?from=1070&limit=8` | 7.9 ms | 3.7 ms | 1.9 ms | 2.9 ms |
| `/chain?from=1070&limit=8` | 5.7 ms | 4.0 ms | 2.6 ms | 5.5 ms |
| `/chain/search?q=continuite` | 292.6 ms | 269.6 ms | 185.8 ms | 244.0 ms |
| `/bridges/status` | **14.25 s** | 14.29 s | **243 ms** | 14.30 s |
| `/ai/events?max_seconds=2` | 2.31 s client / 7.0 ms 1er chunk | idem | 2.28 s / 3.0 ms | 2.31 s / 3.9 ms |

`/chain?from_index=1070&limit=8` renvoie **count=1** : 1070–1073 privés, seul **1074** public — authz, pas un bug d’index.

Bridges OVH : 5/6 ok, bitcoin `timeout` (2 s). AWS : 5/6 ok, ethereum **429**. Le 14 s GRA11 = latence egress RPC (max des 6 pings parallèles), plus 6×15 s séquentiels. AWS prouve le parallèle (~84–243 ms).

SSE : **répond**. 254 ne pouvait pas l’inclure.

### Probe OpenAPI GET (104 appels / nœud, timeout 8 s, 8 threads)

| Nœud | ok | fail | http 0 (timeout) | dur_ns moy |
|---|---|---|---|---|
| OVH1 | **87** | 17 | **9** | 1 611 269 865 |
| OVH2 | **87** | 17 | **9** | 1 616 710 450 |
| AWS3 | **96** | 8 | **0** | **461 900 352** |
| OVH4 | **87** | 17 | **9** | 1 608 171 511 |

254 : OVH 14 ok / **78** timeout ; AWS 88 ok.  
Les 9 timeout GRA11 sont encore les lectures livre **sans** `limit` (`/chain`, `/chain/blocks`, `/export`, `/explorer`, `/block-sizes`) + `/bridges/status` + les variantes stream/status **dans le même burst 8 connexions**. En séquentiel juste après, `/chain/status` client ~6.2 s / **serveur 4.7–6.2 ms** : la file d’accept GRA11, pas l’index.

Fails « sains » (AWS3, 8) : 401 clés/authz/groups, 422 webauthn sans `name`, **403 replica** (allowlist cloud IP), **404 `/chain/block/1073`** (privé).

AWS slowest utiles : `/chain/blocks` **868 ms** serveur (liste complète, compat), `/chain` 827 ms, `/export` 669 ms, `/explorer` 736 ms. **`/chain/stream` 1 ms** serveur.

ConceptID FR/EN/ES : **overlap 0** (1 nœud / langue). Pas un PASS.

### Mémoire + KCG + replica

`POST /ai/memo` HTTPS `:8443` : HTTP **200**, client **675 493 824 ns**, serveur **213 389 542 ns**.  
Bloc **index 1075** hash `d71676d3f1cb8dbd3302cbe185ffc216236adde7bb4bd527fa78bd34e73df0f8` graph `ai_memo_f94564946d8f`.

KCG : publish `K_1af98b2bb80d1f05` + consult `C_cc2cf66125732512` + use **200** (`consumer_address` fourni).

`POST /p2p/replica/run?include_files=false` depuis **127.0.0.1 OVH1** : HTTP 200, serveur **2 850 209 483 ns**.  
OVH2 / AWS3 / OVH4 : height 1075→**1076**, même tip `d71676d3…`, chunk `1075-1075`, imported 1, duplicates 0, 0 erreur.

Après replica, `/chain/status` ×4 (séquentiel) :

| Nœud | height | last_index | last_hash | chain_valid | verify_mode | srv ns |
|---|---|---|---|---|---|---|
| OVH1 | 1076 | 1075 | `d71676d3f1cb8dbd…` | true | tip | **2 508 479** |
| OVH2 | 1076 | 1075 | idem | true | tip | **2 160 934** |
| AWS3 | 1076 | 1075 | idem | true | tip | **1 587 520** |
| OVH4 | 1076 | 1075 | idem | true | tip | **3 132 843** |

`GET /ai/memo/1075` confirme la leçon 257 (tags `257,stream,book_index,live_probe,memory`).

---

## 5. Ce qui n’est toujours pas démontré

- ConceptID FR/EN/ES : overlap **0**.
- BFT / failover / partition.
- Stockage binaire de l’historique (253).
- GRA11 : 8 GET parallèles saturent encore la file TCP même si le handler est O(1).
- `/chain` / `/export` / `/explorer` / `/block-sizes` **sans** `limit` restent O(n) (compat). Le chemin neuf est `/chain/stream` + `from_index`/`limit`.
- Bridges GRA11 ~14 s (egress RPC public), pas le livre.
