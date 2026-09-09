# 298 — `main` poussé ; follow-main SSH depuis ce Mac FAIL

**GitHub `origin/main` = `bd72d319fe2a7979aca11fdf18f108bab5e196cb`** (297 + 298).  
Push `HEAD:main` mesuré. PR #84 non mergée.

## Règle enfreinte (tour précédent)

**Règle 16 ingest** : le fichier `/tmp/artcb_turn_prompt.txt` était écrit, mais le JSON disait `ARTCB_INGEST_PROMPT_FILE unset`. Cause réelle : **pas de `ARTCB_API_KEY`**. Le skip reason mentait.

Corrigé : `api_key_missing` + `ingest_path`. Relu ce tour : `ingest_skipped=true`, `ingest_reason=api_key_missing`. Prompt **pas** on-chain.

Aussi : **complet = live** (règles 1–3 / 39). Terminer sans push + follow-main mesuré = incomplet.

## Ce qui est sur GitHub

- `ecdf10b` feat(297) Mac replica + N adaptatif
- `bd72d31` fix(298) ingest honnête + protocole 37–40

Mac local `:8001` **healthy** SHA `bd72d31` (même que `origin/main`).

## Propagate VMs

`scripts/artcb_sync_official_nodes.py --install` : follow_rc **2** ×4 = `missing_ssh_key`.  
Ce Mac n’a que `~/.ssh/artcb_deploy` (GitHub) et `cursor_mac_node`. Pas `artcb_ovh_deploy` / `_2` / `_3` / `_4`.

`:8443` ×4 depuis cet agent = **URLError timeout**. SHA live des 4 VMs = **non mesuré ici**. Les timers `artcb-follow-main` doivent tirer `main` tout seuls. Ne pas inventer leur `git_sha`.

`CERTIFIED_100=false`. N04 FAIL indépendant.

## Thinking (réponse)

| Où | Quoi |
|---|---|
| Cursor Machine | `~/.cursor/projects/<workspace>/agent-transcripts/*.jsonl` = chat + outils. **Pas** le CoT privé du modèle. |
| Cursor Cloud | Backend Cursor. **Pas** le disque Mac. **Pas** ARTCB. |
| UI `showThinkingBlocks` | Affichage seulement. |
| ARTCB | Seulement si POST mémo. `includes_thinking=false`. |
