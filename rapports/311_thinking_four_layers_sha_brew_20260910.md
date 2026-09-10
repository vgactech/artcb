# R311 — 4 couches thinking + pont SHA + brew swtpm

**UTC :** 2026-09-10T21:55:00Z  
**CERTIFIED_100 :** `false`

## Verdict architecture

| Couche | Contenu | ARTCB ? |
|--------|---------|---------|
| 1 CoT privé | interne modèle | **Non** |
| 2 UI Thinking Cursor | panneau chat | **Pas automatiquement** |
| 3 Hook `afterAgentThought` | `stdin.text` → `latest.raw.txt` | fichier local **toujours** |
| 4 Mémo private | si `ARTCB_INGEST_THINKING=1` | **Oui** si HTTP OK |

Égalité **UI (2) = hook (3)** : **`NOT_PROVEN_BY_ARCHITECTURE`**.  
Égalité **hook (3) → fichier → ARTCB (4)** : mesurable via `sha256_raw`.

## Outils

- Hook : écrit `latest.raw.txt` + `latest.meta.json` + `latest.md`
- `scripts/artcb_verify_thinking_bridge.py` `[--fetch-artcb]`
- `stop` → `scripts/artcb_turn_bundle_ingest.py` via `.cursor/hooks/stop_turn_bundle.py`

## Brew (parallèle)

macOS 12 : pas de bottle `swtpm` → build source. `ftp.gnu.org` timeout → cache miroir `mirrors.kernel.org`.  
`m4` installé ; toolchain `autoconf/automake/libtool` puis `libtpms`/`swtpm` ensuite.
