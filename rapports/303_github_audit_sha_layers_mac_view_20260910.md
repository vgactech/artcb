# 303 — audit GitHub SHA layers + Mac view N=5 local ≠ quorum

**2026-09-10T14:51:00Z.** `CERTIFIED_100=false`. Jamais wipe. Genesis / rescue / `install.sh` **non**. `includes_thinking=false`. Ingest ce tour : HTTP **409** `equivocation`, `ingest_skipped=true`, prompt **pas** on-chain.

## Accord avec l’audit GitHub

L’audit de `vgactech/artcb` `852f0e24134c15315bf29f2477af5fbbcfc67dd0` est **correct** :

| Couche | SHA | Rôle |
|--------|-----|------|
| Commit GitHub 302b | `852f0e2…` | Documente le follow-main de `07ed590` |
| SHA applicatif prouvé par le rapport 302b | `07ed59000139e81c7cffcd4d2fb810927c05f1b2` | Code `fix(302)` sur les nœuds **au moment 302b** |
| Runtime mesuré ensuite (log local `logs/302b_follow_main_after_docs.json`, **hors** artefact GitHub 302b) | `852f0e2…` ×5 | **Nouvel état post-302b** — le dépôt 302b ne le prouve pas à lui seul |
| Runtime ce tour (HTTPS domaines) | `852f0e2…` ×4 seeds + Mac `:8001` | Mesure 2026-09-10T14:47:59Z |

**852f0e2 = commit d’audit. 07ed590 = SHA que 302b prouve. Si le health dit 852f0e2, c’est un état postérieur.**

GitHub combined status `852f0e2` : `state=pending`, `total_count=0`, `statuses=[]`, check-runs `total=0`. **Pas** « CI verte ».

## Ce que ce tour mesure (pas un PREPARE)

### Seeds (HTTPS `artcb.me` / `n2` / `n3` / `n4`)

IPv4 direct `:22` / `:8000` / `:8443` = **Connection refused** depuis ce LAN (ICMP Port Unreachable via `192.168.152.177`). Ce n’est **pas** une preuve que les VM sont mortes : les domaines 443 répondent.

| Nœud | HTTP | `git_sha` | height | tip | `/pbft/view` n | replicas inclut Mac | view stockée | primary stocké |
|------|------|-----------|--------|-----|----------------|---------------------|--------------|----------------|
| ovh-node-1 | 200 | `852f0e2…` | **1133** | `cc0bf8a1…` | **5** | oui | 15 | ovh-node-4 |
| ovh-node-2 | 200 | `852f0e2…` | **1133** | `cc0bf8a1…` | **5** | oui | 15 | ovh-node-4 |
| aws-node-3 | 200 | `852f0e2…` | **1133** | `cc0bf8a1…` | **5** | oui | 15 | ovh-node-4 |
| ovh-node-4 | 200 | `852f0e2…` | **1133** | `cc0bf8a1…` | **5** | oui | 15 | ovh-node-4 |

`chain_valid=true` ×4. Wipe **non**. Livre inchangé **1133**.

`primary_of(15)` avec N=5 = `official_pbft_replica_ids()[15 % 5]` = **ovh-node-1**. Le champ `primary` stocké reste **ovh-node-4** (reste de l’époque N=4 où `15 % 4 = 3`). Label membership N=5 ≠ primary rebindé. **Pas** une preuve de quorum Mac.

`prepared_count=0` ×4 au probe. Compteurs `committed`/`certificate` 43–45 = historique, **pas** un round N=5 avec le Mac.

### Mac `:8001`

Processus **avant** restart : lancé **2026-09-09T20:00:51** (local). `/health.git_sha` = `git rev-parse HEAD` = `852f0e2`, mais `/pbft/view` **n=4** sans `mac-node-local` dans `replicas`. **git_sha health ≠ modules chargés en mémoire.**

`launchctl kickstart -k` a arrêté uvicorn. Relance immédiate : `doppler run` **FAIL** (`restricted secrets` / `MAC_SUDO_PASSWORD`). KeepAlive en boucle. Livre local **6** lignes conservé.

Correctif : `scripts/artcb_mac_doppler_run.sh` — noms seulement, skip `MAC_SUDO_PASSWORD`, `--only-secrets` le reste. Jamais `--plain`. launchd `me.artcb.node` **UP**.

**Après** reload :

| Champ | Valeur |
|-------|--------|
| HTTP | 200 |
| `git_sha` | `852f0e2…` |
| `/pbft/view` n | **5** |
| replicas | 4 seeds + `mac-node-local` |
| view locale | **0** (store local neuf ≠ view 15 des seeds) |
| height locale | **6** tip `01a5f743…` ≠ livre officiel 1133 |
| prepared/commit/cert | **0 / 0 / 0** |

HTTP 200 + n=5 dans le JSON Mac = **identité logique chargée**. Ce n’est **pas** PREPARE/COMMIT, pas de P2P inbound (RFC1918, `replica_peer_allowed("10.234.49.2")=false`, tunnel `rfc1918_requires_tunnel`), pas de quorum N=5, pas de VIEW-CHANGE N=5 mesuré.

### Ingest

Bootstrap IPv4 `:8443` = URLError (filtre LAN). Retry `ARTCB_API_URL=https://artcb.me` : health 200, height 1133, ingest **409** `equivocation`, `ingest_skipped=true`. Dernier mémo index **1131** HTTP 200 chars 1096 sha256 `97b69d1e…` (lecture, pas une écriture de ce prompt).

## Verdict

**CERTIFICATION RETENUE.** `CERTIFIED_100=false`.

Validé : couches SHA 07ed590 vs 852f0e2 ; follow-main 302b ; seeds HTTPS 200 + livre 1133 ; N=5 dans `/pbft/view` seeds et Mac **après** reload ; 409 = rejet ; CI GitHub vide ; Doppler restricted ne doit pas tuer `doppler run`.

Non prouvé : Mac membre du protocole (PREPARE → COMMIT → quorum → view-change → persistance partagée). SSH follow-main depuis ce LAN = **NOT_REACHABLE** (port 22 filtré) ; les timers seeds existent, non relancés ici.

Logs : `logs/303_sha_layers_mac_restart.json`, `logs/303_ssh_process_status.json`, traces `data/trace/ns.jsonl`.
