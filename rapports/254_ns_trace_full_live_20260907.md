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

`pytest tests/test_e2e254_ns_trace.py` — *(mesuré)*

---

## 3. Interdit toujours

Wipe `blocks.jsonl`. `install.sh`. Genesis. `init-node`. Rescue. Afficher le token. Mélanger Doppler. Inventer un PASS ConceptID ou BFT.

---

## 4. Live (à remplir)

SHA live / `origin/main` : *(mesuré)*  
Hauteurs ×4 : *(mesuré)*  
Probe GET ok/fail ×4 : *(mesuré)*  
ConceptID FR∩EN∩ES : *(mesuré)*  
Mémo 254 gravé + replica : *(mesuré)*  
`GET /trace` summary : *(mesuré)*  
Lenteurs / 5xx / 403 replica : *(mesuré)*
