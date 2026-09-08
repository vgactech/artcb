# 268 — Agent Memory Runtime + P8 prepared view-change

Date live : **2026-09-08T17:01:37Z**. SHA mesuré : **`960f069ef70af68df01d56797ab855535e6281c0` ×4** = `origin/main` du run.

## Accord avec l’audit indépendant

- PBFT public exclusif R266 : **oui**, code + live `78cd8d6` (≠ main actuel au moment 266).
- **Pas 100 %** : pas de preuve formelle ; P3–P18 Byzantine (PREPARE/COMMIT contradictoires, replay long, NEW-VIEW forgé, multi-view campagne) **non** exécutés ici.
- Mémoire agent : **agent-médiée**. `ingest_platform_hook=false`. Cursor ≠ Claude ≠ ChatGPT.
- Premier ingest 267 brut : SHA **230b8eb5**. Recert P0 : **b66f51a9** ×4, bloc 1096 `40b16afa…`, height 1097.

## P0 — SHA avant R268 code

| Champ | Valeur |
|---|---|
| ingest recert | `logs/267_ingest_20260908T165526Z.json` |
| index | **1096** |
| hash | `40b16afaefa9e42a5b38882ee49364947ca6fb6f038ab9515c53c96d0f5f6758` |
| after_sha ×4 | `b66f51a9…` |

Consolidation 266 : `logs/266_pbft_cert_consolidated.json` — premier `PBFT_LIVE_E2E_PASS=false`, retries V01/V02 **PASS**, SHA testé `78cd8d6` ≠ main.

## Code

1. Prepared certificate : PRE-PREPARE signé + PREPARE Q=3 uniques. `select_new_view_value` ignore les P-set faibles. Conflit de digest au même seq → pas de choix. `must_repropose_prepared` si Y.
2. Agent protocol : `GET /api/v1/agent/bootstrap`, `POST /api/v1/agent/register`, `POST /api/v1/agent/events` (idempotent `event_id`).
3. MCP : `artcb_agent_bootstrap`, `artcb_memory_event`.
4. pytest : `tests/test_e2e268_agent_pbft.py` + PBFT + MCP → **53 passed**.

## Live P8 (fichier `logs/268_p8_20260908T165949Z.json`)

| Champ | Mesure |
|---|---|
| sha_equal | true (`960f069e` ×4) |
| X seq / digest | 1097 / `c79319fbebfbd0459f3d1fac617e9a02c2646cc4641e4e5a86cfbbf891070bf3` |
| view avant | 6, primary aws-node-3 |
| prepared_proofs | ×4 true |
| select kept_x | true (proof true) |
| propose Y | HTTP **409** `must_repropose_prepared` |
| repropose X | HTTP 200 |
| cert + writes | true ×4 |
| after | height **1098**, view **7**, primary **ovh-node-4**, tip = digest X |
| ok | **true** |

## Live agent protocol (`logs/268_agent_20260908T170137Z.json`)

| Champ | Mesure |
|---|---|
| bootstrap | HTTP 200, protocol `268-agent-memory-runtime`, `platform_hook=false` |
| register | `agent_320497e7c08d` |
| event 1 | committed, block **1098**, hash `9c67ac0627c7938110f25ad9723e23db38aafc0d1a0b610059ef7cef248571cf` |
| event 2 | `already_committed`, same_block true |
| includes_thinking | false |
| after height ×4 | **1099** même tip |
| cert 1098 | Q=3, 4 commits, ok ×4 |
| ok | **true** |

## Non livré (dette assumée)

Adapters Claude/ChatGPT/Gemini, mTLS mesh, enforcement API des capabilities `wallet:export`, ACL multi-agent, campagne Byzantine P3–P18, preuve formelle.

## Verdict

PBFT finality live : **fortement démontrée** (R266) + **P8 live PASS** (prepared → VIEW-CHANGE → X conservé, Y refusé).  
Certification 100 % : **NON**.  
Mémoire universelle indépendante du LLM : **fondation R268 live PASS**, pas encore universelle.
