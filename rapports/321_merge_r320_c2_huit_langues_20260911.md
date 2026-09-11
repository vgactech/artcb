# R321 — merge R320 + C2 philologie 8 langues (2026-09-11T21:05:00Z)

`CERTIFIED_100=false`

## Merge R320 / PR #85

| Check | Result |
| --- | --- |
| `origin/main` before | `99cb1d7` (R319) |
| Branch | `devin/1789159300-r320-concept-sync-session-soak` @ `a27f1c2` |
| Local verify | **39** pytest PASS (320 network + session + 319) |
| C2-D script | **PASS** local-socket ACBN (not WAN) |
| Live `/concepts/resolve` pre-deploy | 404 (honest) |
| Merge | **FF** `99cb1d7..a27f1c2` → `main` |
| PR #85 | closed (merged) |

### Audit verdict (aligned with operator)

- C2-D: **PASS — TCP locale** ; **OPEN** WAN / 4 nœuds / P2P `.arcb`
- Session: TTL 1800 + idle 900 + device + revoke/logout-all **PASS code/tests** ; persist/restart **OPEN** (in-memory)
- Autonomie agent ≠ accès total (write Bearer on publish)

## R321 — 8 langues (L1 + L4)

UI locales + Latin: **FR EN ES PT IT RU LA ZH**

| Level | Status | Measure |
| --- | --- | --- |
| L1 lexical ×8 | **PASS** | all → ConceptID `K3e7dc01c5cf83cd8` (code `C2`) |
| synonym `automobile` | **PASS** | R319 GAP closed |
| false friend `autonomie` | **PASS** | no C2 |
| FR conj `car` | **PASS** | not vehicle |
| L4 phrases ×8 | **PASS** | bag `U1C2E3` → `Ke410ef3b8d2bddd5` |
| C2-E FR/ZH/RU agents | **PASS** pytest | same ConceptID without shared text |
| C2-D WAN | **OPEN** | after follow-main re-probe |
| Full morphology RU/ZH | **PARTIAL** | table lemmas, not a full morphological analyzer |

Tokenizer R321: Latin + Cyrillic + CJK; ASCII short keys token-exact (`auto` ⊄ `autonomie`).

## Still OPEN (P0 file kept)

- C2-D multi-hôte / 4 seeds
- Session store across process restart + replay soak
- Catch-up past hole 716
- TPM / swtpm macOS 12
- HBP / anti-Sybil full
- `CERTIFIED_100`

## Artifacts

- `logs/321_c2_langage_latest.json`
- tests: `tests/test_e2e319_c2_langage_battery.py` (extended)
