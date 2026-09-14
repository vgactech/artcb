# R342 — Bannière BETA TEST dans l’en-tête UI

**UTC:** 2026-09-14T10:15:00Z  
**Commit:** `ee57058`  
**Live:** `https://artcb.me/` sert `index-BtHzgi7y.js` + badge **BETA TEST** (mesuré)

## Texte (FR)

> **BETA TEST** — Version de test — pas encore la version officielle. L’inauguration avec les vrais coins validés aura lieu prochainement.

## Fix follow-main

`scripts/artcb_follow_main.sh` : ~~exclude `frontend/dist/`~~ barré — le SPA tracké doit se déployer aussi en overlay tarball.
