# PROMPT Replit 184 — plus d’unshallow, Publish le tip

Les logs `20260901T112644Z_22` / `113052Z_23` : 182/183 **checkout tip=9b9b2e4** (plus de rewind 178), puis Autoscale **SIGTERM** pendant `git fetch --unshallow` (~17 s) et avant uvicorn. Deuxième instance tuée pareil. `/` en 500 le temps que le shim perde le port.

184 :
- clone `--depth 1` du tip, **jamais** `--unshallow`
- shim `allow_reuse_address` + HEAD + wait `/live` 200
- `ARTCB_FAST_BOOT=1` : pas de sleep bande passante, pas d’import faiss au boot

## Publishing

```text
Deployment type: Autoscale
Public directory: (vide)
Run command: bash scripts/replit_autoscale.sh
Build command: (vide)
```

`ARTCB_REPLIT_PIN_SHA` = SHA complet de `fix(184): Autoscale skip unshallow so healthcheck can pass` sur `cursor/replit-sync-ready-16d8`. **Publish / Redeploy**.

Logs OK (< ~15 s) : `shim_ready /live=200` → `checkout tip=` → `launching uvicorn`. Interdit : `unshallow`, `checkout pin=4cb2943`, `Création venv`.

OVH1 n’est pas modifié. OVH2 / AWS3 / OVH4 reçoivent ce même tip (git pull + restart). Pas d’init-node Replit.
