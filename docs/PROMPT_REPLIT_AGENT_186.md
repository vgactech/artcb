# PROMPT Replit 186 — ne plus cloner GitHub au boot Autoscale

Log `20260901T114712Z` :

```text
11:47:13 shim_ready /live=200
11:47:14 Cloning into '/tmp/artcb-src-21'...
11:47:30 SIGTERM
11:47:36 checkout tip=781fe76  (184, pas 185)
11:49:28 python=.pythonlibs
11:51:32 launching uvicorn
```

Le clone GitHub (~16 s) se fait tuer. Le Python venv (faiss AVX) retarde le pick. 186 : **pas de clone** (snapshot Publish), `.pythonlibs` avant `$HOME/venv`, import Python limité à 8 s.

## Publishing

```text
Run command: bash scripts/replit_autoscale.sh
ARTCB_REPLIT_PIN_SHA=<SHA complet de fix(186) sur GitHub>
```

Publish / Redeploy. Logs : `keep snapshot no_clone` puis `launching uvicorn`. Interdit : `Cloning into`, `unshallow`, `checkout pin=4cb2943`. Pas d’init-node.
