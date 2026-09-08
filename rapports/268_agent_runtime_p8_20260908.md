# 268 — Agent Memory Runtime + P8 prepared view-change

Date : **2026-09-08T16:55:26Z** (P0 ingest) puis live P8/agent après follow-main.

## Accord avec l’audit indépendant

- PBFT public exclusif R266 : **oui, code + live 78cd8d6**.
- **Pas 100 %** : P-set faible avant ce commit ; pas de preuve formelle ; pas tous les scénarios Byzantine PREPARE/COMMIT/replay live.
- Mémoire agent : **agent-médiée**. `ingest_platform_hook=false`. Cursor ≠ Claude ≠ ChatGPT.
- Dernier ingest 267 brut : SHA **230b8eb5**. `origin/main` au début de ce tour : **b66f51a9** ×4 déjà déployé.

## P0 — SHA

Ingest live **sur b66f51a9 ×4** (ferme l’écart 230b8eb vs main au moment du run) :

| Champ | Valeur |
|---|---|
| index | **1096** |
| hash | `40b16afaefa9e42a5b38882ee49364947ca6fb6f038ab9515c53c96d0f5f6758` |
| cert ×4 | true |
| fichier | `logs/267_ingest_20260908T165526Z.json` |

Consolidation 266 : `logs/266_pbft_cert_consolidated.json` (premier `PBFT_LIVE_E2E_PASS=false`, retries V01 PASS, SHA testé `78cd8d6` ≠ main actuel).

## Code R268 (ce commit)

1. **Prepared certificate** : PRE-PREPARE signé + PREPARE Q=3 uniques dans le P-set / VC265. `select_new_view_value` ignore les entrées faibles. Conflit de digest au même seq → pas de choix arbitraire. `must_repropose_prepared` si le primary propose Y.
2. **Agent protocol** : `GET /api/v1/agent/bootstrap`, `POST /api/v1/agent/register`, `POST /api/v1/agent/events` (idempotent `event_id`).
3. **MCP** : `artcb_agent_bootstrap`, `artcb_memory_event`.
4. Tests : `tests/test_e2e268_agent_pbft.py`.

**Non livré ici** (dette assumée, pas un PASS) : adapters Claude/ChatGPT/Gemini, mTLS mesh, capabilities `wallet:export` séparées en enforcement API, ACL multi-agent complète, campagne P3–P18 Byzantine longue, preuve formelle.

## Verdict

PBFT finality live : **fortement démontrée** (R266) + P8 **codé et pytest**.  
Certification 100 % : **NON**.  
Mémoire universelle indépendante du LLM : **fondation R268, pas encore universelle**.
