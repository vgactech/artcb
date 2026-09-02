# Rapport 207 — `main` suivi automatiquement par tous les nœuds et tous les clones

**Horodatage début :** 2026-09-02T21:05:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false` × 4, non modifié)  
**Branche PR :** `cursor/ovh4-ssh-keepbook-568e` (suite de #54)  
**Demande opérateur :** fusionner les mises à jour dans `main`, déployer `main` sur **tous** les serveurs, et que les nœuds **et** les clones reçoivent les suivantes **sans le répéter**.

Rien n’est inventé. PEM / `dp.st.…` / mots de passe **non imprimés**. Rescue **non utilisé**. PR **#51 non fusionnée**.

## 1. Pourquoi ça bloquait

| Fait | Mesure |
|------|--------|
| Live 4 nœuds déjà sur le même SHA | `ad017bca05c2e3799c7dcd120ca1797968d499b6` branche `main` |
| GitHub `origin/main` agent | **même SHA** `ad017bca05c2e3799c7dcd120ca1797968d499b6` |
| Travail #54 (SSH OVH4, pub rotée, inject sans rescue) | **pas encore** sur GitHub `main` (PR draft) |
| `git fetch` HTTPS sur OVH2/OVH4 (hist. 199/206) | HTTP **401** / « could not read Username » — le dépôt est pourtant public |
| Redéploiement | toujours un ordre manuel SSH + bundle. Aucun timer. `install.sh` n’installait pas de suivi |
| Règle workspace | « ne pas déployer `main` sur `:34` sans ordre » — **ordre explicite donné** ce tour : tous les serveurs + auto-suivi |

Sans fusion `main` **et** sans timer, chaque agent recommence le keep-book à la main. C’est le blocage.

## 2. Ce qui a été ajouté (pour ne plus le répéter)

| Fichier | Rôle |
|---------|------|
| `scripts/artcb_follow_main.sh` | fetch `origin/main` ; nœud officiel = reset keep-book + `release.env` + restart ; clone = ff-only si `main` propre ; repli tarball si 401 |
| `scripts/artcb-follow-main.service` + `.timer` | toutes les **5 min** sur nœud officiel |
| `scripts/install_follow_main.sh` | pose le timer (systemd officiel, sinon user 15 min, sinon cron) |
| `install.sh` étape 7/8 | tout nouveau `git clone && bash install.sh` installe le suivi |
| `scripts/artcb_sync_official_nodes.py` | SSH les 4 VM, pose le timer, mesure la matrice (JSON dans `logs/207_*`) |
| `docs/FOLLOW_MAIN.md` | notice opérateur / cloneur |
| `OFFICIAL_COMPUTE_NODE_IDS` + `PUBLIC_HEALTH_URLS` | registre canonique des 4 compute |

**Keep-book :** jamais `install.sh` / genesis / init-node / rescue / wipe `blocks.jsonl`.

## 3. Matrice live AVANT pose du timer (mesurée 2026-09-02 ~21:05Z)

Bootstrap OVH1 `https://152.228.144.34:8443` : HTTP 200, `git_sha=ad017bca05c2e3799c7dcd120ca1797968d499b6`, `git_branch=main`, PQC ML-DSA-65, `certified_distributed_mainnet=false`.

| Nœud | IP | Doppler | `/health` HTTP | HTTPS :8443 | domaine | SHA | branche | certif |
|------|----|---------|----------------|-------------|---------|-----|---------|--------|
| ovh-node-1 | 152.228.144.34 | artcb-blockchain | 200 | 200 | `https://artcb.me/health` 200 | `ad017bca05c2e3799c7dcd120ca1797968d499b6` | main | false |
| ovh-node-2 | 151.80.107.29 | artcb-2 | 200 | 200 | `https://n2.artcb.me/health` 200 | **même** | main | false |
| aws-node-3 | 51.44.222.232 | artcb3 | 200 | 200 | `https://n3.artcb.me/health` 200 | **même** | main | false |
| ovh-node-4 | 91.134.45.8 | artcb-4 | 200 | 200 | `https://n4.artcb.me/health` 200 | **même** | main | false |

Livre (mesures 206 / 199, non réécrit ici) : height **1**, `last_hash` `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce`, `chain_valid=true`.

SSH clés agent (présentes, jamais affichées) : `~/.ssh/artcb_ovh_deploy`, `artcb_ovh_node_2`, `artcb_aws_node_3`, `artcb_ovh_node_4`.

## 4. PRs ouvertes — ce qui entre / ce qui reste dehors

| PR | Sujet | Décision |
|----|-------|----------|
| **#54** | OVH4 SSH sans rescue + keep-book + **ce suivi auto** | **à fusionner dans `main`** (cette branche) |
| **#53** | docs secrets OVH4 | docs seulement, fusionnable à part ; **pas bloquant** pour le suivi |
| **#52** | D-055 biométrie WebAuthn + frontend | **autre sujet** (2490+ lignes UI). Pas fusionné ici pour ne pas casser le live |
| **#51** | OVH2 **rescue** | **interdit** — contredit « sans rescue ». **not merged** |
| **#1** | rapport expert ancien | hors sujet |

`gh` est lecture seule : pas de bouton merge CLI. Tentative : `git push origin HEAD:main` si la protection le permet ; sinon merge UI de #54.

## 5. Ce qu’un cloneur doit recevoir

```
git clone https://github.com/vgactech/artcb.git
cd artcb && bash install.sh
```

`install.sh` appelle `install_follow_main.sh` :

- si la machine devient nœud officiel (`/etc/artcb/official_node` ou `artcb.service`) → timer 5 min + reset keep-book
- sinon → timer user / cron, **ff-only** uniquement sur `main` propre

Après une mise à jour de GitHub `main`, le clone **propre** sur `main` avance tout seul. Un clone avec des commits locaux n’est **pas** écrasé.

## 6. Données encore à collecter dans ce tour (après commit)

Le JSON `logs/207_follow_main_*.json` doit contenir pour chaque nœud :

- health HTTP / HTTPS / domaine (code, SHA, branche, certif, PQC)
- `hostname`, `git rev-parse HEAD`, `wc -l data/chain/blocks.jsonl`
- `cat /etc/artcb/official_node`
- `systemctl is-enabled artcb-follow-main.timer`
- résultat `git ls-remote` (401 ou SHA) — pour prouver le repli tarball
- sortie d’un run `artcb_follow_main.sh` (`FETCH_METHOD=…`, `DEPLOYED_SHA=…`)

Cette section est mise à jour **après** `python3 scripts/artcb_sync_official_nodes.py --install` (keep-book, pas de wipe).

## 7. Interdits respectés

- Pas de rescue.
- Pas de wipe `blocks.jsonl`.
- Pas de `certified_distributed_mainnet=true`.
- Pas de fusion #51.
- Token / PEM non affichés.
- OVH1 inclus dans l’auto-suivi **sur ordre explicite**.
