# R319 — C2 langage IA E2E battery + balance authz (2026-09-11T20:20:00Z)

`CERTIFIED_100=false`

## Namespaces (doc fix)

| Id | Meaning |
| --- | --- |
| `C2` | Lexicon **object code** for vehicle lemmas (`voiture`/`car`/`coche` → IR `O1C2`) |
| `K3e7dc01c5cf83cd8` | Concrete **ConceptID** hash from type+sym |
| `C2-A`…`C2-D` | **Test ladder** levels — not ConceptIDs |

These are not two conflicting concepts.

## Session TTL (code, not UI storage)

- `_SESSION_TTL = 1800` (30 min) in `src/api/auth_routes.py`
- UI still showing a token ≠ server session valid
- Full T0…T+expiry matrix (logout/revoke/device) still **OPEN** for live multi-hour soak

## Authz P0

| Check | Local pytest | Live pre-deploy (`artcb.me` @ e750c93) |
| --- | --- | --- |
| `/auth/me` anon | — | 200 `authenticated=false` |
| `/wallet/list` anon | 401 | 401 |
| `/wallet/balance/X` anon | **401** (R319) | **200** until follow-main |
| session A → balance B | **403** | after deploy |
| session TTL config | 1800 | 1800 |

Opt-in only: `ARTCB_WALLET_BALANCE_PUBLIC=1`.

## C2 ladder (measured)

Script: `scripts/artcb_c2_langage_e2e.py`  
Tests: `tests/test_e2e319_c2_langage_battery.py`

| Level | Status | Note |
| --- | --- | --- |
| C2-A lexical + adversarial | **PASS** | vehicle→`K3e7dc01…`; `avion`≠; `verificar`≠; `automobile` synonym **GAP** honest |
| C2-B phrases | **PASS** | FR/EN/ES phrases contain vehicle ConceptID (R319 EN `the car` fix) |
| C2-C reason/packet | **PASS** | local AgentChannel; packet has no human text; derive new K |
| C2-D A→network→B | **PARTIAL** | cold B missing without `.arcb` sync; warm prior OK; live memo 409; **not** serious E2E PASS |

UI locales present: `fr en zh es pt it ru`. Semantically probed for vehicle: `fr en es` only.

## R319 EN “car” regression fix

R318 blanket skip of multi-token `car` broke English *"The car consumes…"*.  
Now: English determiner + `car` → vehicle C2; FR *"… car …"* conjunction still skipped; grammar REASON `"car "` skipped for EN vehicle NP.

## Still OPEN

- C2-D cold path / concept-store sync over P2P
- Catch-up past Mac/seed hole 716
- Session expiry soak + revoke + multi-device
- swtpm macOS 12 incomplete
- Relation-sentence FR/EN ConceptID full convergence (C2-C EN relation id still diverges)
- `CERTIFIED_100`

## Artifacts

- `logs/319_c2_langage_latest.json`
- `logs/319_auth_live_probe.json`
