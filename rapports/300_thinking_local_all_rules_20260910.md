# 300 — thinking local + toutes les règles + Bob §4 barré

Horodatage **2026-09-10T00:05:00Z**. `CERTIFIED_100=false`. PR #84 non mergée.

## Question : écrire le thinking dans un fichier au lieu du chat

**Découverte (docs Cursor, pas une invention) :**

1. Il n’existe **pas** de réglage « thinking fichier à la place du chat ».
2. Le CoT privé est produit sur le **backend Cursor** (`data-use` : même avec une clé API perso, les requêtes passent par leur backend).
3. `showThinkingBlocks` = **affichage** CLI seulement.
4. Transcripts Machine `agent-transcripts/*.jsonl` = chat + outils, **pas** le CoT privé.
5. Seul mécanisme officiel automatique : hook **`afterAgentThought`** (copie du thinking **surfacé**, après coup).

Donc « 100 % du raisonnement intact avant ARTCB » **au sens CoT privé** = **impossible** avec Cursor.  
« 100 % du thinking **surfacé** + 100 % du journal de processus agent » = **oui**, local, gitignored, jamais on-chain.

## Dispositif installé

- `.cursor/hooks.json` : `afterAgentThought`, `preCompact`, `sessionStart`
- `data/trace/agent_thoughts.jsonl` (hook)
- `data/trace/agent_reasoning.jsonl` (`scripts/artcb_reason_log.py`)
- `data/trace/precompact.jsonl` (moment où la mémoire **dans** le tour disparaît)
- `.cursor/rules/artcb-read-all.mdc` `alwaysApply: true` — index de **tous** les fichiers

Oubli opérateur figé : `mac-node-local.mdc` / `aws-node-3.mdc` / `ovh-node-4.mdc` étaient `alwaysApply: false` ; `AUTO_PROMPT_ARTCB` n’est pas un `.mdc`. L’agent ne les voyait pas tout seul.

## Bob, même machine

§1–3 et §5 **confirmés** sur ce Mac : plist `me.artcb.node` KeepAlive/RunAtLoad, `doppler run --project artcb-1 --config prd`, uvicorn `:8001`, cwd playground.  
~~§4 observateur hors PBFT.~~ Barré. Replica R297b. Bob a réussi une question **locale sans toucher**. Ce n’est pas un autre ordinateur.

## Mesures

Voir JSON health Mac et pytest T-E77 de ce tour. Ingest : dire `ingest_skipped` si HTTP 0.

## [2026-09-10T00:22:00Z] live OVH1 mesuré

- OVH1 `:8443` **200** `git_sha=4fe76ddc8ff739b0de69950d7c865ce897217896` branch `main` height **1133** tip `cc0bf8a1…` `chain_valid=true`.
- SHA live mesurés 2026-09-10T00:22:00Z : OVH1/OVH2/OVH4/Mac = `4fe76dd`. **AWS3 = `05d7030` (en retard)**. Ne pas inventer l’égalité ×4.

## [2026-09-10T00:25:00Z] follow-main mesuré ×4 + Mac

SSH `ARTCB_FOLLOW_MODE=official bash scripts/artcb_follow_main.sh` rc=0 ×4. Health **200** SHA **`c24f097fb9fc9cde979ee5497c736229ecd2c43d`** = `origin/main` sur OVH1, OVH2, AWS3 (rattrapé depuis `05d7030`), OVH4, Mac `:8001`. Ingest 409 `not_prepared` inchangé. `CERTIFIED_100=false`.
- Ingest ce prompt : `ingest_http=409` `commit:not_prepared` — `ingest_skipped=true`. Prompt **pas** on-chain. `includes_thinking=false`. Archive sha256 `e2cf58d1…` chars 2674.
- Mac `:8001` même SHA `4fe76dd`. Pytest T-E77 10 passed.
- `CERTIFIED_100=false`. N04 last FAIL.
