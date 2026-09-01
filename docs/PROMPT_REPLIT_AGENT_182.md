# PROMPT Replit 182 — PIN + Publish, garder le tip

Les logs `20260901T110529Z_24` / `…111131Z_25` : le shim 181 démarre, clone la branche, puis **rewind** :

```text
HEAD is now at 4cb2943 audit(178)
checkout pin=4cb2943...
release sha=4cb2943...
```

Uvicorn 178 n’arrive que ~5 min plus tard → Autoscale SIGTERM → boucle. Les `connection refused` / `500` des premières secondes sont **normaux**.

## Publishing (obligatoire)

```text
Deployment type: Autoscale
Public directory: (vide)
Run command: bash scripts/replit_autoscale.sh
Build command: (vide)
```

Secrets à garder : `SESSION_SECRET`, `ARTCB_REPLIT_PIN_SHA`.

`ARTCB_REPLIT_PIN_SHA` = le **SHA complet** du commit 182 sur `cursor/replit-sync-ready-16d8` (message `fix(182): never rewind Autoscale to an old PIN`). Copier depuis GitHub/Cursor. **Pas** `4cb2943…`.

Puis **Publish / Redeploy** (un Restart ne remplace pas l’image).

## Logs OK (< ~30 s)

```text
[step=shim] live_shim ...
[step=git_sync] checkout tip=...
[step=git_sync] release sha=...
[step=uvicorn] launching uvicorn python=...
```

Interdit dans les logs : `checkout pin=4cb2943`, `[1/6] Création venv Python isolé`.

## Vérif après Publish

```text
/live                  → 200, sans phase=replit_shim
/ready                 → 503, bootstrap_mode
/api/v1/health         → 200, git_sha = tip 182, release_integrity=ok
/api/v1/wallet/list    → 503, pas 404
```

Interdit : Static pages, Public directory, passphrase wallet, `init-node`, liboqs, OVH1.
