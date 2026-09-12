# Rapport 328 — Dual ledger + import public ovh1 + stall watchdog

**Date:** 2026-09-12T19:20:00Z  
**Issue:** [#86](https://github.com/vgactech/artcb/issues/86)  
**Commit (code):** `70694050b4db7efac8e7a12bdc21e59b26b6637a`  
**CERTIFIED_100:** `false`

## Problème

R327 a corrigé la **construction** publique (`public_last_index+1`) mais `write_certified_block` / `import_extending_block` utilisaient encore `height()` du journal mixte. Sur ovh1, un suffixe privé (~700+ lignes) bloquait l’import du bloc public certifié 1141 (`wrote=false`) alors que n2/n3/n4 l’avaient.

Hypothèse Mac+n4 pour le stall 30h : **NOT_ESTABLISHED** (cert 1140 Q=3 sans Mac).  
Hypothèse timer vs entry-path : à trancher via `GET /pbft/public-tip-watchdog` (`pending_prepares` → a ; sinon b).

## Correctifs code

1. **`src/artcb/chain/split_ledger.py`** — migration one-shot `blocks.jsonl` → `public/` + `private/` ; legacy **conservé** (jamais wipe).
2. **`ChainManager`** — `write_certified` / import public = tip public + append livre public ; privés = livre privé ; lookup `get_by_consensus_index`.
3. **`public_tip_watchdog`** — diagnostic a/b + auto VIEW-CHANGE contrôlé (`ARTCB_PUBLIC_TIP_AUTO_VC`, seuil `ARTCB_PUBLIC_TIP_STALL_SEC`).
4. **Tests** `tests/test_r328_split_ledger_public_import.py` — suffixe privé, trous/doublons, migrate sans wipe.

## Critères Issue #86 (sortie)

| ID | Statut attendu au premier deploy |
|----|----------------------------------|
| A/B construct public tip | PASS (R327 + R328) |
| C ovh1 import + private suffix | **à mesurer live** après follow-main |
| D no wipe | PASS (legacy preserved) |
| E–H auto VC / PREPARE/COMMIT/Q | **partiel** — watchdog + routes ; preuve auto VC live encore OPEN |
| I tip×4 | **à mesurer** |
| J restart | OPEN |
| K métriques séparées | `ledger_mode=split_v1` dans `/chain/status` |
| L trous/doublons | PASS unit |
| M SHA live | **à mesurer** |
| N rapport + `logs/R328/measurement.json` | ce fichier + script |
| O CERTIFIED_100 | **false** jusqu’à preuves complètes |

## Mesure

```bash
PYTHONPATH=src python3 scripts/artcb_r328_live_measure.py
```

Artefact : `logs/R328/measurement.json`

## Interdits respectés

- Pas de wipe `blocks.jsonl`
- Pas d’invention du bloc 717
- Pas de retrait Mac
- Pas de changement arbitraire n/f/q
