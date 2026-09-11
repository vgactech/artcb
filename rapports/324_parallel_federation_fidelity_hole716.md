# R324 — parallèle (fédération apex + fidélité + trou 716)

`CERTIFIED_100=false`

## ARTCB = mémoire auto Cursor ?

**NON.** Pas un interruptor on/off. Chaque tour : recharger `main` + liste OPEN. Documenté ≠ résolu. Règle opérateur : ne jamais s'arrêter sur un seul axe.

## Bugs corrigés en cours de route

1. **Fédération host skip** — `n2.artcb.me.endswith(".artcb.me")` sautait le publisher apex. Skip = exact Host match seulement. Test `test_e2e324_federation_host_skip.py`.
2. **Fidélité beaucoup/peu** — bag `U1C2E3` sans intensité → même ConceptID (`Ke410ef3…`) = `FAIL_COLLAPSE`. Ajout modifiers `QH`/`QL` → `U1C2E3QH` = `K493b83061fa228b9` vs `U1C2E3QL` = `K1b3569768e79c9ef`. L4×8 reste convergent sur QH.

## Mesures (scripts)

- `scripts/artcb_r324_parallel_measure.py` — B hop=1 après warm, fidélité, coût dictionnaire, inventaire 716
- `scripts/artcb_r324_hole716_inventory.py` — live : **HOLE_CONFIRMED_NO_CHILD** (717 absent ×4, aucun enfant de tip716)

## Ouverts

- Publisher-death B live après follow-main du fix fédération (mesure post-déploiement)
- Catch-up au-delà de 716 : **ne pas inventer** ; trou de production
- Fan-out write n2–n4 / SSH:22 / swtpm / HBP / PQC enforced
