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

## 4. Live (après script)

_À remplir avec les JSON mesurés — ne pas inventer._
