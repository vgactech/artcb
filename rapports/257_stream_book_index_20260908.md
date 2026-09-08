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

## 4. Live (à mesurer après follow-main)

Réservé aux mesures réelles : `/chain/status` ns ×4, `/chain/stream` ns ×4, `/bridges/status` ns ×4, probe OpenAPI, mémo 257, tip après replica.

---

## 5. Ce qui n’est toujours pas démontré

- ConceptID FR/EN/ES : overlap 0 (252/255).
- BFT / failover / partition.
- Stockage binaire de l’historique (253 : transition block plus tard).
- Saturation GRA11 sous charge parallèle : à **re-mesurer** après l’index ; AWS3 tenait déjà.
