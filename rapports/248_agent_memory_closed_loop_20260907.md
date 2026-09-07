# Rapport 248 — L’agent a utilisé ARTCB comme mémoire (boucle fermée)

**Date :** 2026-09-07T20:51:00Z  
**GO :** « utilise ARTCB en temps réel comme un utilisateur réel » — pas un essai ChatGPT.  
**Pas de wipe. Pas de D-0xx. GO-E produce off.**  
**Contact :** `official@artcb.space`

---

## 0. Ce que le live a dit **avant** d’écrire (pas le chat)

SHA live = `origin/main` = `c1d8027da4c9ae79d0cd96974e492747034b5479`.  
OVH1 height **8**, tip `f646c510…`. `chain_valid` true.

| Route | HTTP | Mesure |
|---|---|---|
| `GET /ai/memory` | 200 | **`count=0`** |
| `GET /ai/context` | 200 | « Chaîne: 8 blocs \| **0 memos IA** » |
| `GET /kcg/knowledge` | 200 | **`count=0`** |
| `GET /kcg/stats` | 200 | 0 consult, 0 use |
| `GET /chain/search?q=D-024` | 200 | « Rapport 247 » score **0.235** (faux positif) |
| `GET /chain/search?q=memoire agent` | 200 | « Le livre doit grandir » (texte GO-247) |
| `GET /graph` + `POST /decode` idx 5–7 | 200 | source_text GO-247 **décodable** (disque graphes) |

Les routes `/ai/memo`, `/ai/memory`, `/ai/context`, `/kcg/*` **existaient déjà** sur `c1d8027`. Elles n’avaient **jamais** été utilisées en live.  
Les blocs 5–7 sont des gravures keep-book. Ce n’est pas une mémoire de projet.

`POST /search` / `GET /chain/search` = `SequenceMatcher` in-memory (CDC MVP). Ce n’est pas un embedding. « 21 millions » ne retrouve pas D-024.

---

## 1. Utilisation réelle (utilisateur agent)

`POST /api/v1/ai/memo` `visibility=public` `memo_type=lesson` `session_id=sess_248_agent_memory`  
`X-ARTCB-Agent-Id: cursor-cloud-agent`

| Champ | Valeur mesurée |
|---|---|
| HTTP | 200 |
| `memo_stored` | true |
| `block_index` | **8** |
| `block_hash` | `623d6e7875e5ab24ffc12d2d7978aa0485ab77aa63070217f0438144df93a69a` |
| `graph_id` | `ai_memo_05a709e390c3` |
| `pol_score` | 0.75 |
| `node_count` | 18 |

Puis KCG **sur le même graphe** :

| Route | HTTP | ID |
|---|---|---|
| `POST /kcg/publish` | 200 | `knowledge_id=K_0b844c034302754d` |
| `POST /kcg/consult` | 200 | `consult_id=C_29205a61fac0d61f` |
| `POST /kcg/use` | 200 | `usage_id=U_c62056e085885f4c` `delta_utility=1.0` |

KCG disque OVH1 : `knowledge.jsonl` = **1** ligne, `events.jsonl` = **2** lignes (consult+use).  
KCG = JSONL **local au nœud**, pas un tip partagé.

---

## 2. Relire (le test de continuité)

| Route | Après |
|---|---|
| `GET /ai/memory` | **count=1**, lesson #8, tags memory/kcg/continuity/248/live |
| `GET /ai/context` | « Chaîne: **9** blocs \| **1** memos IA » + `[lesson #8]` |
| `GET /ai/memo/8` | `content_available` ; texte lesson + snapshot « 8 blocs \| 0 memos IA » au moment de la gravure |
| `GET /chain/search?q=continuite` | score **1.0** sur la phrase du mémo, bloc 8 |
| `GET /chain/search?q=D-024` | score **1.0** sur la phrase du mémo qui **cite** le faux positif ; l’ancien 0.235 est encore là |
| `/chain/status` OVH1 | height **9**, last = `623d6e78…`, `chain_valid` true |
| SSH `blocks.jsonl` | **9** lignes ; idx 0–7 inchangés ; idx 8 `learning_source=ai:memo:lesson` |

OVH2 / AWS3 / OVH4 : height **5** / `27350024…` (import 222). Pas un wipe.

---

## 3. Où était l’information — et où elle n’était pas

| Couche | Rang | Contient déjà « pourquoi ARTCB / 21M / D-024 » ? | Utilisée par l’agent avant 248 ? |
|---|---|---|---|
| D-0xx | 1 | oui (fichiers) | non (reconstruit depuis le chat) |
| Code `/ai/*` `/kcg/*` | 3 | l’API oui ; le **contenu** non | **non** (0 mémo, 0 K) |
| Tests | 4 | suites locales | hors sujet live |
| Live livre | 5 | hashes + graph_id ; texte via GraphStore disque | `/store` dummy, pas `/ai/memo` |
| Rapports 001–247 | 6 | oui, trop, versions multiples | lu par morceaux, traité comme vérité |
| Chat / essai 14 sections | — | reconstruction | **c’est ça le gaspillage** |

Le texte ChatGPT de ce soir a raison sur le **problème**. Il a tort s’il présente KCG/PoUC/Reasoning Fee comme **mémoire déjà en service** : live KCG était à 0 jusqu’à ce mémo. `1c2b873` (brief Bob) était déjà périmé en 246. `h_adult` live = **0**.

---

## 4. Réflexe désormais câblé (rang 3, pas une D-0xx)

`scripts/artcb_live_bootstrap.py` expose maintenant : `chain_height`, `last_hash`, `ai_memory_count`, `last_memo_index`, `kcg_knowledge_count`, tête de `/ai/context`.  
Règle workspace : si `ai_memory_count` > 0 → lire `GET /ai/memo/{last_memo_index}` **avant** le chat.  
Connaissance nouvelle : `/ai/memo` + `/kcg/publish`, pas `/store` « write N ».

Test : `test_compact_memory_snapshot_uses_last_memo_not_chat`.

---

## 5. Matrice

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| Agent = user traçable `sess_` / agent-id | 233 | — | `require_write_actor` | e2e233 | header `cursor-cloud-agent` sur mémo 8 |
| Mémo IA = bloc | CDC AI | — | `POST /ai/memo` | ce live | idx 8 `623d6e78…` |
| KCG publish/consult/use | GO-F | — | `kcg_routes` | ce live | `K_0b844c03` C+U |
| Recherche ≠ vérité | CDC MVP | — | `SequenceMatcher` | live 248 | D-024 faux positif puis hit auto-citation |
| Import store/mémo n’étend pas les pairs | 222 | — | `decide_public_import` | live 248 | 2/3/4 restent `27350024` |
| Bootstrap lit la mémoire | — | — | `compact_memory_snapshot` | test 168 | pas encore déployé (SHA live toujours `c1d8027`) |

Pas de D-0xx. Packet KCG inter-nœuds : **toujours pas** une route.
