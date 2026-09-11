# R322 — bootstrap clone + session durable + C2-D multi-hôte (2026-09-11T21:55:00Z)

`CERTIFIED_100=false`

## Objectif utilisateur

Clone GitHub → install auto deps OS/runtime → live 5 machines sans les pièges connus.

## Livré

### 1. Bootstrap zero-touch
- `scripts/artcb_bootstrap.sh` — apt/brew idempotent puis `install.sh` + verify
- README pointe sur bootstrap (install.sh reste le cœur runtime)
- Oublis couverts : python3-venv, node/npm, build-essential, cmake, libssl, pkg-config

### 2. Sessions durables
- `src/api/session_store.py` → `{ARTCB_DATA_DIR}/auth/sessions.json` (hashes only)
- Survive clear mémoire / restart process (pytest PASS)
- revoke / logout / idle flush disque

### 3. C2-D multi-hôte
- Script `scripts/artcb_c2d_multihote_live.py`
- Mesure live (pré-fédération deploy) :
  - health **5/5** SHA `324d070` aligné
  - WAN cold resolve via `https://artcb.me` **PASS** + offline **PASS**
  - publish+self-resolve : **ovh1 + Mac PASS**
  - n2/n3/n4 self-store : **401** sans clé write Doppler locale (SSH:22 timeout)
- R322 ajoute **fédération one-hop** `/concepts/resolve` (`ARTCB_CONCEPT_FEDERATE=1`) pour que n2–n4 servent après publish ovh1 sans clé write distante

### 4. Toujours OPEN (honnête)
| Item | État |
| --- | --- |
| Fan-out store natif n2/n3/n4 sans fédération | dépend Doppler/SSH |
| Catch-up Mac au-delà du trou seed **716** | **OPEN** (pas d'invention de blocs) |
| swtpm macOS 12 | **OPEN** (doctor) |
| HBP / anti-Sybil complet | **OPEN** |
| `CERTIFIED_100` | **FALSE** |

## Clone futur

```bash
git clone https://github.com/vgactech/artcb.git && cd artcb
bash scripts/artcb_bootstrap.sh
source .venv/bin/activate
PYTHONPATH=src uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

## Artefacts
- `logs/322_c2d_multihote_latest.json`
- tests `test_e2e322_session_persist.py`, `test_e2e322_concept_federation.py`

## Update 2026-09-11T22:00:00Z — client federation

SHA `9e2dbde`. Live re-mesure :

- `sha_aligned_5` = true (`fc1cad4` puis follow vers `9e2dbde` en cours)
- `self_resolve_ok_hosts` = **5/5** (n2/n3/n4 via fallback client → artcb.me)
- `offline_persist` = true ×5
- `c2d_multihote_pass` = true
- write fan-out natif n2–n4 stores = encore OPEN (401 / SSH timeout)
- CERTIFIED_100=false
