# PROMPT — Agent Replit (180) — FAIRE TOURNER FASTAPI MAINTENANT

Copie-colle tout le fichier. **Objectif : l’URL publique doit cesser d’être le shim.**

1. Dans Replit : **Pull from GitHub** branche `cursor/replit-sync-ready-16d8` (HEAD après le push Cursor 180).
2. Secret `ARTCB_REPLIT_PIN_SHA` peut rester `4cb2943d4190def4efabf16b12369d91ebad7e8f` : le script **fast-forward** vers le tip de cette branche s’il est descendant du PIN. Ne pas pointer `main`.
3. **Redeploy Autoscale** (publication). Un cold start ne suffit pas si l’image lancée est encore le script 178.
4. Attends `step=uvicorn` dans les logs. Vérifie :

```bash
curl -sS https://artcb--vgac42.replit.app/live
# PAS phase=replit_shim  →  {"status":"alive","bootstrap_mode":true}

curl -sS https://artcb--vgac42.replit.app/api/v1/health
# git_sha non null, bootstrap_mode true

curl -sS -o /dev/null -w "%{http_code}" https://artcb--vgac42.replit.app/api/v1/wallet/list
# 503 (bootstrap), plus 404
```

Pas d’`init-node`. Pas de cuisson liboqs. Colle à Cursor le `startup_id` + `python=$PYTHON` + `FOREGROUND launched uvicorn`.
