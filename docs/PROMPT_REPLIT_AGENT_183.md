# PROMPT Replit 183 — Publish le tip (Python Replit, pas Nix)

Le workflow local tourne déjà **182** (`255d599`) + Python `/home/runner/venv/bin/python3`.
La sonde **publique** `https://artcb--vgac42.replit.app` sert FastAPI, mais encore **178** :

```text
git_sha=4cb2943d4190def4efabf16b12369d91ebad7e8f
pin_sha=4cb2943d4190def4efabf16b12369d91ebad7e8f
/live 200 sans phase=replit_shim
```

183 ajoute le sélecteur Python du workflow : venv Replit / `.pythonlibs` **avant** le `python3` Nix. **Aucun** `python3 -m venv`.

## Publishing

```text
Deployment type: Autoscale
Public directory: (vide)
Run command: bash scripts/replit_autoscale.sh
Build command: (vide)
```

Secrets : `SESSION_SECRET`, `ARTCB_REPLIT_PIN_SHA`.

`ARTCB_REPLIT_PIN_SHA` = le **SHA complet** du commit `fix(183): prefer Replit Python over Nix, never create a venv` sur `cursor/replit-sync-ready-16d8`. **Pas** `4cb2943…`, **pas** seulement `255d599` si 183 est le tip.

Puis **Publish / Redeploy**.

## Logs OK (< ~30 s)

```text
[step=git_sync] checkout tip=...
[step=uvicorn] launching uvicorn python=/home/runner/venv/bin/python3
```

(ou `.pythonlibs/bin/python3` sur Autoscale — pas de création de venv)

Interdit : `checkout pin=4cb2943`, `Création venv Python isolé`.

## Vérif

```text
/live                  → 200, sans phase=replit_shim
/ready                 → 503 bootstrap
/api/v1/health         → git_sha = tip 183, release_integrity=ok
/api/v1/wallet/list    → 503, pas 404
```

Interdit : init-node, liboqs, OVH1, Static pages.
