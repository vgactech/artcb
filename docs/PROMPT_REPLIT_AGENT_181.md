# PROMPT Replit 181 — UN redeploy, PAS de venv

**Superseded by 182.** Le 181 a bien démarré le shim, puis un clone `--depth 1` a fait échouer `merge-base` et a rewind vers `4cb2943` (178). Voir `docs/PROMPT_REPLIT_AGENT_182.md`.

Le log `20260901T104032Z_20` : **11 min** `Création venv` → Autoscale **TERM** → nouveau start → encore TERM. Le script **178** tournait encore (`4cb2943` exact, pas 180).

**Ne plus** laisser `ARTCB_REPLIT_PIN_SHA=4cb2943…`. Publier 182 et pointer le PIN sur le SHA 182.

**À faire tout de suite :**

1. Secret `ARTCB_REPLIT_PIN_SHA` = `4cb2943d4190def4efabf16b12369d91ebad7e8f` (inchangé, ancêtre OK) **ou** le SHA 181 que Cursor affiche.
2. GitHub → Pull `cursor/replit-sync-ready-16d8`.
3. **Redeploy Autoscale** (Publish). Le `run` doit être `bash scripts/replit_autoscale.sh`.
4. Dans les logs tu dois voir en **moins de 30 s** : `live_shim` puis `launching uvicorn`. **Pas** `[1/6] Création venv`.

```bash
curl -sS https://artcb--vgac42.replit.app/live
# {"status":"alive","bootstrap_mode":true}  sans replit_shim
```

Interdit : `python3 -m venv` sur Autoscale. Interdit init-node tant que `/live` n’est pas FastAPI.
