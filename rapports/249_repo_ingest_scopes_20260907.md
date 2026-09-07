# Rapport 249 — Ingestion repo → livre (public / org / groupe / privé)

**Date :** 2026-09-07  
**GO :** envoyer la totalité du travail déjà fait sur le livre, classé, et bâtir ce qui manque pour que l’agent s’en serve.  
**Pas de wipe. Pas de D-0xx. GO-E produce off.**  
**Contact :** `official@artcb.space`

Les mesures live (hauteurs, hashes, totaux) sont dans §4 — remplies **après** exécution, jamais inventées.

---

## 0. Règle d’organisation

| Scope logique | Chaîne (`visibility`) | Pourquoi |
|---|---|---|
| `public` | `public` | rapports, src, tests, specs, simulations — déjà publics sur git |
| `organization` | `private` + `organization_id=org_artcb_memory` | ops / deploy / follow-main. Body **pas** P2P. Hash dans le catalogue public |
| `group` | `private` + `group_id=group_artcb_agents` | AUTO_PROMPT, règles agent, `.cursor/` |
| `private` | `private` | logs, data_local, secrets **catalogue only** |

Secrets (`.env`, `*.pem`, `artcb_` lines) : listés dans le catalogue (path + sha256), **corps jamais inliné**.  
Binaires (pdf, images) : idem.  
ORG/GROUP genesis humains : l’agent **ne peut pas** créer d’ORG/GROUP (`agent_cannot_admin_org_or_group`). Scopes logiques en attendant un GO humain. Les ORG Alice / 220 existantes **ne sont pas** écrasées.

Live avant : height **9**, tip `623d6e78…`, 1 mémo IA, KCG 1, 0 groupes, plusieurs ORG déjà ancrées.

---

## 1. Ce qui a été développé (rang 3)

- `src/artcb/memory/repo_scope.py` — classification + redaction
- `src/artcb/memory/repo_ingest.py` — catalogue 100 % des `git ls-files`, lots, graphe IR réversible, index jsonl
- `POST /api/v1/ai/ingest-batch` — grave un lot **sans contributors** (pas le throttle 60 s minage)
- `GET /api/v1/ai/ingest/catalog` + `GET /api/v1/ai/ingest/file?path=`
- `scripts/artcb_ingest_repo_live.py` — fallback `POST /ai/memo` si l’endpoint n’est pas encore sur le nœud
- Tests `tests/test_e2e250_repo_ingest.py`

---

## 2. Inventaire local (git ls-files, ce workspace)

Mesuré avant push : **1441** fichiers suivis, **28.77 Mo**.  
Lots après cap 28 k : **1063** (public / private / group / organization).  
Corps UTF-8 : 1405. Secrets catalogue-only : 29. Binaires : 7.

---

## 3. Matrice

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| Catalogue 100 % paths+sha256 | GO opérateur 249 | — | `repo_ingest.catalog_lines` | e2e250 | §4 |
| Public dans public | ACL + 222 | — | `chain_visibility` | e2e250 | §4 |
| Org/groupe hors P2P | domaines 218 | — | private + symbols | e2e250 | §4 |
| Secrets non inlinés | D-029 | — | `is_secret_path` / redact | e2e250 | §4 |
| Agent ≠ fondateur ORG | 233 / 236 | — | `_require_human` | déjà | 403 attendu |

---

## 4. Live (mesuré 2026-09-07T21:17:51Z → 21:20Z)

`POST /api/v1/ai/ingest-batch` × **1065**, **0 fail**, via `ingest-batch` (pas le fallback memo).  
SHA working-tree agent : `7174761`. SHA `/health` nœud : toujours `c1d8027` (overlay keep-book, pas un merge `main`).  
Livre : height **1074**, `last_index` **1073**, `last_hash` `3d1231cde101b70f77f852f3b7db698a0b8d8558fa6b747e51189450659c3acf`, `chain_valid` **true**.  
SSH `blocks.jsonl` = **1074** lignes. idx **0–8 inchangés** (`b8a7d5ef` … `623d6e78`).

| Visibilité chaîne | Blocs (SSH) |
|---|---|
| public | **717** |
| private | **357** |

Lots par scope : public **708** + organization **3** + group **5** + private **349** = 1065.

Index `GET /ai/ingest/catalog` : **3539** lignes (fichiers + chunks + lignes catalogue).  
`by_scope` index : public 2990 / organization 18 / group 15 / private 516.

KCG catalogue : `K_40b33b30244c9a4c` graph `ing_repo_catalog_cat_0_ef6075b1`. KCG total **2** (lesson 248 + catalogue).

Relu avec la même clé (après correctif « bearer ingest ⇒ relire le privé ») :

| path | scope | chunks | chars | head |
|---|---|---|---|---|
| `AUTO_PROMPT_ARTCB` | **group** | 4 | 89257 | « TU DOIS METTRE À JOUR CETTE PROMPT… » |
| `DECISIONS_UTILISATEUR_ARTCB` | public | 1 | 12844 | « # DÉCISIONS UTILISATEUR — ARTCB » |
| `src/artcb/chain/manager.py` | public | 2 | 28979 | docstring manager |
| `.cursor/rules/artcb-live-node.mdc` | **group** | 1 | 2635 | règle nœud live |
| `deploy/artcb_ovh_node_2.pub` | **organization** | 1 | 99 | clé **publique** SSH |
| `rapports/248_…md` | public | 1 | 5302 | rapport 248 |

OVH2 / AWS3 / OVH4 : height **5** / `27350024…` (import 222). Pas un wipe.  
GO-E produce off. Pas de D-0xx. Contact `official@artcb.space`.

Le follow-main officiel peut **revenir** le code overlay vers `origin/main` ; les **1074 blocs** et les graphes disque restent. Merger ce PR pour que `/ai/ingest/*` tienne après le timer.
