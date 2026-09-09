# 299 — règles 11–15 (jamais supprimer) + Mac replica ; push obligatoire

Horodatage : **2026-09-10T23:35:00Z**.  
`CERTIFIED_100=false`. N04 FAIL indépendant. PR **#84** non mergée.

## Règle que l’opérateur voulait que l’agent retrouve seul

**Règles 11–15** (pas seulement 16) : interdiction de supprimer / compacte / réécrire en place.  
Révocation = `~~barré~~` + horodatage UTC. Nouveau texte **à la suite**.  
**Idem dans le code** (`# ~~…~~` puis nouveau bloc) — règle 41 (2026-09-10T23:05:00Z).

Violation répétée : `.cursor/rules/mac-node-local.mdc` et `node_registry.py` avaient été compactés.  
Texte original rétabli + commentaires horodatés. Section « Interdits » du fichier compacté **conservée** (2026-09-10T23:35:00Z), pas remplacée.

## `/tmp/artcb_turn_prompt.txt`

Deux fautes distinctes :

1. **Règle 16** : écrire le `user_query` **brut intégral**. Un résumé dans ce fichier = compactage (11–12 + 16).
2. **Règle 16 skip** : si le fichier est là mais sans clé, `ingest_reason=api_key_missing` — jamais « FILE unset ».

Ce tour : fichier = query brute. Archive append-only `data/trace/turn_prompts.jsonl` (`ts_ns`, texte, sha256).  
Ingest on-chain : voir JSON bootstrap de ce tour (si `ingest_skipped=true`, le prompt **n’est pas** sur ARTCB).

## Thinking — réponse claire

| Où | Quoi | Trouvé ? |
|---|---|---|
| Cursor Machine | `~/.cursor/projects/Users-deyi-bob-playground/agent-transcripts/*.jsonl` = chat + tool calls | **Oui** |
| Cursor Machine | CoT privé du modèle (thinking interne) | **Non** — pas sur le disque Mac |
| Cursor Cloud | backend Cursor | **Oui** (pas le Mac, pas ARTCB) |
| UI `showThinkingBlocks` | affichage seulement | pas un store |
| ARTCB | seulement si POST mémo | `includes_thinking=false` |

Perte de mémoire : **chaque nouveau tour**. Le chat n’est pas le protocole. Relire `alwaysApply` + `AUTO_PROMPT_ARTCB` de la première à la dernière ligne **avant** tout autre travail.

## Mac = nœud comme OVH/AWS (pas d’isolation)

~~`live_enrolled=False` / FOLLOW_MAIN = 4 VMs only.~~ Refusé 2026-09-09T21:55:00Z.  
`official_pbft_replica_ids()` inclut `mac-node-local`. N=5 f=1 Q=3. N adaptatif.

## Mesures de ce tour (ne pas inventer)

- Mac `:8001` **200** SHA **`c6dc2048da981eb6ea00b047d3d33a9b7d329e81`** healthy.
- `:8443` / `:8000` / `:22` ×4 depuis ce Mac = **TimeoutError**.
- `artcb.me` DNS `gaierror` / 443 refused — SHA VM **non mesuré ici**.
- SSH keys Doppler → `~/.ssh/artcb_ovh_*` **écrites** (411–420 octets). Follow-main SSH depuis ce LAN = timeout TCP 22.
- `~/.artcb/cursor_agent.env` écrit (0600). Token jamais affiché.
- Pytest T-E76 : `test_e2e299` + 297 + 298 + 296 = **10 passed**.

Les timers `artcb-follow-main` des 4 VMs doivent tirer `origin/main` après ce push. Ne pas inventer leur `git_sha`.

## [2026-09-10T23:48:00Z] mesures après commit `369b5ec`

- `git push origin HEAD:main` : `c6dc204..369b5ec`. `HEAD` = `origin/main` = **`369b5ec6d0c9c9ffd56cef68d9105c591360bbb7`**.
- Mac `:8001` **200** SHA **`369b5ec`** (clone local, même SHA que GitHub).
- Ingest : `key_present=true` (`env_or_local_file`), `ingest_attempted=true`, `ingest_http=0`, `ingest_error=URLError`, `ingest_skipped=true`. Prompt **pas** on-chain. Archive locale sha256 `cfb2db03…` chars 2873.
- Follow-main SSH depuis ce Mac : `ssh: connect to host … port 22: Operation timed out` **rc=255 ×4** (ConnectTimeout=8s). SHA VM **non mesuré**. Timers `artcb-follow-main` sur les VMs restent le chemin de pull.
- `CERTIFIED_100=false`. Health Mac `certified_distributed_mainnet=true` **n’est pas** CERTIFIED_100.
