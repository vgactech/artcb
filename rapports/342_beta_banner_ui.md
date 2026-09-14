# R342 — Bannière BETA TEST dans l’en-tête UI

**UTC:** 2026-09-14T10:15:00Z  
**Commit:** `ee57058`  
**Live:** `https://artcb.me/` sert `index-BtHzgi7y.js` + badge **BETA TEST** (mesuré)

## Texte (FR)

> **BETA TEST** — Version de test — pas encore la version officielle. L’inauguration avec les vrais coins validés aura lieu prochainement.

## Fix follow-main

`scripts/artcb_follow_main.sh` : ~~exclude `frontend/dist/`~~ barré — le SPA tracké doit se déployer aussi en overlay tarball.

## R342b — Reprobe propagation (2026-09-14T16:28:44Z)

Divergence historique **conservée** mais classée :

| Artefact | Statut |
|---|---|
| `logs/R342/live_probe.json` | **SUPERSEDED_STALE** (mesuré avant follow-main ; `DfbuIJFE` / beta=false / sha `ed159ff`) |
| `logs/R342/deploy_poll.json` | preuve intermédiaire PASS (`ee57058` + BETA) |
| `logs/R342/live_propagation_reprobe.json` | **référence actuelle** |

### Chaîne mesurée maintenant

```text
origin/main = 86f4dcb…
    ↓
/health ×4 = 86f4dcb… (égal)
    ↓
HTTP artcb.me / n2 / n3 / n4
    ↓
index-BtHzgi7y.js + index-BaQ-WNEh.css
    ↓
BETA TEST dans JS+CSS = true
    ↓
ancien index-DfbuIJFE.js = absent
```

`propagation_live_proven_now=true`  
**CERTIFIED_100=false** (BETA ≠ inauguration coins validés ; #86/#77/etc. ouverts).

