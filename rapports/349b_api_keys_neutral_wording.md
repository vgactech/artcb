# R349b — Wording API keys neutre (pas de `vgactech2`)

**UTC:** 2026-09-14T18:20:00Z (approx.)  
**Parent:** R349a `aaadd3b5128e7545798bf2513cf1b5ac2624d916`  
**CERTIFIED_100:** false

## Objectif

Neutraliser les exemples UI qui citaient `vgactech2`, sans créer/recréer de wallet, sans toucher aux associations USER↔NODE / USER↔WALLET.

## Changements

`frontend/src/pages/ApiKeys.tsx` :

| Avant | Après |
| --- | --- |
| « ex. vgactech2 » (hint session) | « connectez d’abord le wallet » |
| « session (ex. vgactech2) » | « wallet connecté (session) » |
| placeholder `Cursor vgactech2 test` | `Cursor / agent de développement` |
| checklist « ex. vgactech2 » | « wallet déjà existant » |

Aucune création automatique de wallet. Aucune modification de seed / clés.

## Live (mesuré)

- `/health.git_sha` apex = `aaadd3b5128e7545798bf2513cf1b5ac2624d916` (pré-deploy R349b)
- Clé utilisateur `artcb_…` (hors git) : `GET /api/v1/api-keys/me` → **HTTP 200**, label présent, scopes `read,write,mining,admin`
- `GET /api/v1/api-keys/list` avec Bearer `artcb_` → **401** (session `sess_` requise) — correct
- Prompt ingest : `409 not_extending` → `ingest_skipped=true` (honnête)

## Non revendiqué

- USER↔WALLET ownership layer (R349 propre)
- REPLICATED_PROTOCOL USER↔NODE N1…N4
- UNIQUE_HUMAN
- CI verte (commit non signé / combined status vide possible)
- CERTIFIED_100

## Secrets

Seed et token `artcb_` fournis en chat → **ne jamais** git / mémo on-chain / rapport. Fichier local `/tmp/artcb_r349b_vgactech2.env` mode 0600 uniquement. Rotation recommandée si le chat est partagé.
