# R312 — Badge « ARTCB thinking » + E2E partiel

**UTC :** 2026-09-10T23:00:00Z  
**CERTIFIED_100 :** `false`

## UI Cursor « Thought briefly »

**Impossible à renommer** (docs Cursor : `afterAgentThought` observe-only, aucun champ de sortie UI).

## Signal visible à la place

| Signal | Rôle |
|--------|------|
| `data/trace/ARTCB_THINKING.md` | Titre **ARTCB thinking** — prouve capture auto |
| `thinking/latest.raw.txt` + sha256 | Couche 3 mesurable |
| `LAST_ARTCB_SEND.md` | Ce qui a été réellement envoyé |
| Règle user Cursor | Pour futurs users |
| `ARTCB_THINKING_STOP_PING=1` | Opt-in message chat en fin de tour |

## Mesure ce tour

- Hook → fichiers : **PASS** (sha égal)
- Mémo private Mac `:8001` : HTTP **200**, block_index **6**, sha `ab08f304…`
- Public `artcb.me` : **timeout / refused** (réseau)
- Fetch GET memo index : 404 endpoint shape (verify à ajuster) — envoi OK
- Brew : toolchain 4/6 ; `libtpms`/`swtpm` **en build** (`autogen.sh`)
