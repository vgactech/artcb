# R325 — parallel axes (runtime + hard B + 716 + fidelity)

`CERTIFIED_100=false`

## Distinctions (audit opérateur)

- R324 PASS ≠ CERTIFIED_100
- `f739a6b` = code fix mesuré ; `63fdf71+` = docs/branche
- empty GitHub statuses ≠ CI PASS
- fédération ≠ réplication ≠ résilience
- hop=1 local PASS ≠ publisher process arrêté

## A — Runtime

- SHA ×4 alignés sur docs HEAD au moment de la mesure
- **TIP DIVERGE** : artcb.me height ≠ n2/n3/n4 (~1816 vs ~1141) — PARTIAL

## B — Publisher-death hard

- Cold hop=1 vide (après fix mint `∇digest` — plus de collision α1)
- Warm hop=0 → ingest serveur
- hop=1 local n2/n3/n4 **PASS**, `federated=0`
- **publisher_process_stopped=false** (non revendiqué)

## C — Continuité 716

- `HOLE_CONFIRMED_NO_CHILD` / incident **PRODUCTION_CONTINUITY_GAP**
- Jamais inventer 717

## D — Compression + fidélité

- Packet L4 vs UTF-8 inchangé (~85 % sur ce corpus)
- QH/QL/NEG/MOD distincts
- **Pluriel** encore = même bag que beaucoup (OPEN)

## Fix mint R325

~~counter-only α1~~ → `∇{digest12}` pour éviter ConceptID identiques sur textes inconnus différents.
