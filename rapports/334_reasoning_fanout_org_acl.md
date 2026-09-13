# R334 — ReasoningID structurel + fan-out replica + ORG ACL (2026-09-13)

## Verdict

`CERTIFIED_100=false` · `production_ready=false`

Audit ChatGPT sur R333 accepté : set≠multiset et `premises=conclusions` corrigés en **R334-A**.

## R334-A / ReasoningID

- Protocol `r334-canonical-reasoning-v2`
- ConceptID **multiset** (duplicates conservés)
- `premise_concept_ids` ≠ `conclusion_concept_ids` (rôles distincts)
- `relation_triples` dans l’identité
- Tests adversariaux T1–T12 : `tests/test_r334_reasoning_adversarial.py`

## R334-B

Batterie T1–T12 locale **PASS** (pytest).

## R334-C / fan-out write

- ~~dépendance aux API keys Doppler n2–n4~~ — chemin nouveau :
  - `POST /api/v1/concepts/fanout` (Bearer sur le publisher)
  - `POST /api/v1/concepts/peer-ingest` (signature replica officielle)
- Authz : mauvaise clé / clé vide → rejet mesuré
- Direct publish API-key n2–n4 avec clé ovh1 reste **401** (attendu, pas un bypass)

## R334-D / ORG body ACL

- Unit : `test_org_export_acl_knowing_id_is_not_access` — outsider 401/403
- Live probe : export sans session controller refusé (API key ≠ accès body)

## Parallèle non fermé

| Domaine | État |
|--------|------|
| #77 N04 / TPM / C04 | OPEN / NOT_PROVEN (SSH :22 filtrée LAN) |
| #86 tip/VC | PASS partiel ; ORG multi-contrôleur session live = suite |
| Langage C2-D resolve WAN | PASS (remeasure) |
| CERTIFIED_100 | **false** |

## Artefacts

- `src/artcb/reasoning/canonical.py`
- `src/api/concept_routes.py` (`/fanout`, `/peer-ingest`)
- `scripts/artcb_r334_execute_open_p0.py`
- `logs/R334/measurement.json` (après live)
