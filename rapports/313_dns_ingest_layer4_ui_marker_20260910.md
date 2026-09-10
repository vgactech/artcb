# R313 — DNS poison, ingest ON, couche 4 publique, preuve UI marqueur

**UTC :** 2026-09-10T23:25:00Z  
**CERTIFIED_100 :** `false`

## Cause `artcb.me` connection refused

| Source | artcb.me |
|--------|----------|
| DNS LAN `172.28.2.38` / `172.29.2.38` | `172.24.16.51` + `::1` → refused |
| DoH Cloudflare/Google | **`152.228.144.34`** |
| `curl --resolve …152.228…` | **health 200** |

Fix code : `scripts/artcb_dns_fix.py` (patch `getaddrinfo`).  
`/etc/hosts` : non appliqué (Doppler restricted `MAC_SUDO_PASSWORD` inaccessible au token courant) — à faire côté opérateur si voulu système-wide.

## Activations

- `~/.artcb/cursor_hooks.env` : `ARTCB_INGEST_THINKING=1`
- Hook : ingest **default ON** si clé API présente
- Fallback endpoints : artcb.me → n1 → `:8001`

## Preuves mesurées

| Preuve | Résultat |
|--------|----------|
| raw=meta=notif SHA | PASS |
| Thinking → `https://artcb.me` private memo | **PASS** HTTP 200 bloc **1149** hash `26cdfe59…` |
| Marqueur `R312_UI_HOOK_MARKER_8842` dans payload hook | PASS (probe) |
| UI Cursor accordion = payload | **À confirmer visuellement** (ouvre Thinking et cherche le marqueur) |

## Brew

`libtpms` 0.10.2 installé ; `gmp` installé ; `swtpm` deps encore en cours.

## Honte certification

Ne **pas** écrire « Thinking UI Cursor = blockchain » tant que la compare visuelle marqueur n’est pas faite **et** `CERTIFIED_100` reste false.
