# Rapport 254 — Trace nanoseconde + audit live de toutes les surfaces

**Date :** 2026-09-07  
**GO :** se mettre à jour (`252`/`253`), utiliser ARTCB comme mémoire, logger **ns** bout-en-bout y compris le livre, exercer **toutes** les fonctionnalités développées en réel.  
**Pas de wipe. Pas de D-0xx. GO-E produce off.**  
**Contact :** `official@artcb.space`

Les chiffres du §4 sont mesurés après follow-main + probe. Rien n’est inventé.

---

## 0. Rapports distants intégrés

`origin/main` au départ de cette tâche : `2d69704` (live `/health` identique).  
Nouveaux fichiers : `rapports/252 rapport chat et simulation.md`, `rapports/253 rapport chat et simulation.md`.

252 : la réplication 5→1074 est une **vraie** mesure ; le langage IA ConceptID n’est **pas** démontré ; BFT/adversarial non démontré.  
253 : JSON reste le stockage/transport primaire ; recommande flux public/privé **parallèles** + ère binaire sans réécrire l’historique.

Mémoire live lue avant reconstruction : `GET /ai/memo/716` = ingest `ing_repo_batch_b_1f1597b5b4` (pas la leçon 248 — `last_memo_index` pointe le dernier bloc tagué IA). KCG 2 / 1 consult / 1 use. Height **1074** tip `3d1231cd…`.

---

## 1. Code

- `src/artcb/trace/ns.py` — JSONL `data/trace/ns.jsonl` (`ts_ns`, `dur_ns`)
- Middleware HTTP : **chaque** requête, header `X-ARTCB-Trace-Ns`
- Livre : `append_block` → `chain_append` ; `import_extending_block` → `chain_import`
- Flux P2P : `ts_ns` + `rtt_ns`
- `GET /api/v1/trace`
- `scripts/artcb_live_full_probe.py` — tous les GET OpenAPI ×4 nœuds + encode/search/lecture livre
- Tests `tests/test_e2e254_ns_trace.py`

Pas de rewrite du livre en binaire (253 : historique immuable). Pas d’arrêt de nœud / fork adversarial (252 : hors de cette passe).

---

## 2. Tests locaux

`pytest tests/test_e2e254_ns_trace.py tests/test_p2p_api.py tests/test_e2e251_public_propagate.py` : **14 passed**.

---

## 3. Interdit toujours

Wipe `blocks.jsonl`. `install.sh`. Genesis. `init-node`. Rescue. Afficher le token. Mélanger Doppler. Inventer un PASS ConceptID ou BFT.

---

## 4. Live (mesuré 2026-09-07T23:19Z → 23:35Z)

`origin/main` = `/health` ×4 = **`7dce698ef567ce08935e2fb26e1464502d6df174`**. follow-main keep-book ×4, livres restés à 1074 lignes jusqu’au mémo.

### Livre

`POST /ai/memo` (mémoire agent, public) : HTTP **200**, client **909 981 356 ns** (~910 ms), serveur **447 361 728 ns**.  
Nouveau bloc **index 1074** `ce82d755af9549477f761262aeb0243d17d1972e679da0c70efe93facc8f5b48` graph `ai_memo_2dca3353999d`.  
`GET /trace` : **1× `chain_append`**.  
`POST /p2p/replica/run?include_files=false` : HTTP 200 en **4 611 009 906 ns**. Les 4 nœuds à **1075**, même tip `ce82d755…`, `chain_valid=true`.

KCG : publish `K_4c28cc2533921fd7` + consult `C_cc8389f079d6b05d` OK. `/kcg/use` a d’abord 422 (`consumer_address` manquant — faille d’API/docs), puis 200.

Mémoire lue avant : memo **716** = ingest `ing_repo_batch_b_1f1597b5b4`, pas la leçon 248. `last_memo_index` ≠ « dernière leçon ».

### Probe OpenAPI GET (96 appels / nœud, timeout 8 s, 8 threads)

| Nœud | ok | fail | http 0 (timeout) | dur_ns moy |
|---|---|---|---|---|
| OVH1 | 14 | 82 | **78** | 6 719 004 144 |
| OVH2 | 14 | 82 | **78** | 6 728 616 729 |
| AWS3 | **88** | 8 | 0 | **544 299 713** |
| OVH4 | 14 | 82 | **78** | 6 727 553 371 |

En **séquentiel** après le probe, `/chain/status` répond partout (OVH1 client 518 ms / serveur 195 ms). La faille n’est pas « l’API morte » : **8 lectures parallèles saturent OVH GRA11**. AWS3 tient (livre `/chain` 3357 ms, `/chain/blocks` 3310 ms).

Fails « sains » (AWS3) : 401 clés/authz/groups, 422 webauthn sans `name`, **403 replica** (allowlist), **404 `/chain/block/1073`** — le tip d’alors est **private**, le GET public ne le montre pas.

`/api/v1/ai/events` (SSE) n’a **pas** été inclus : il ne rend jamais. C’est une surface développée qui bloque un audit naïf.

### Trace ns OVH1 (`GET /api/v1/trace?limit=2000`)

301 lignes : 300 `http` + 1 `chain_append`. 0 erreur applicative dans le JSONL.  
`dur_ns_min` **648 040** (~0.65 ms). `dur_ns_max` **105 714 601 986** (~**105.7 s**) = `GET /api/v1/bridges/status` (deux fois, HTTP 200).  
Livre : `/chain` 4.07 s, `/export` 3.99 s, `/blocks` 3.97 s, `/explorer` 3.87 s (serveur).  
Header `X-ARTCB-Trace-Ns` présent (health OVH1 44 253 145 ns).

### ConceptID (252) — mesuré localement sur le même code

FR `Kae1edd2bfc1a510d` / EN `K6773930a8ad4f8f3` / ES `Kfac6772568162888`.  
**FR∩EN = 0. FR∩EN∩ES = 0.** Pas un langage convergent. Le probe script a d’abord loggé `ModuleNotFoundError` (import path) — le calcul ci-dessus est l’essai direct `PYTHONPATH=src`.

### Pas démontré (252 / 253, toujours vrai)

BFT, nœud arrêté, fork adversarial, double production, binaire bout-en-bout (JSONL livre inchangé). Pas d’arrêt de machine. Historique 0–1073 non réécrit.
