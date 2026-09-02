# Suivi automatique de `origin/main`

Si GitHub `main` avance, **les 4 nœuds officiels** et **tout clone installé avec `install.sh`** doivent le recevoir **sans nouvel ordre**.

## Qui fait quoi

| Qui | Comment | Ce qui est touché | Ce qui n’est jamais touché |
|-----|---------|-------------------|----------------------------|
| Nœud officiel (OVH1/2, AWS3, OVH4) | timer systemd `artcb-follow-main.timer` toutes les **5 min** | code git, `/etc/artcb/release.env`, restart `artcb` si le SHA change | `data/chain/blocks.jsonl`, `.env`, `.venv`, wallets, rescue |
| Clone (`git clone` + `bash install.sh`) | timer user 15 min **ou** cron `*/15` | `git pull --ff-only` seulement si branche `main` **et** tree propre | travail local, autre branche, livre |
| Clone sale / autre branche | rien (log) | — | tout |
| Forcer un reset keep-book | `ARTCB_FOLLOW_MAIN=1 bash scripts/artcb_follow_main.sh` | comme un nœud officiel | le livre |

Marqueur officiel : fichier `/etc/artcb/official_node` (contenu = `ovh-node-1` …) **ou** unité `artcb.service` activée **ou** `ARTCB_FOLLOW_MODE=official`.

## Pourquoi GitHub 401 sur certaines VM

Le dépôt `vgactech/artcb` est **public**. Sur OVH2/OVH4, `git fetch https://github.com/…` a déjà répondu **HTTP 401** (smart HTTP, pas un wipe). Le script :

1. `git fetch` anonyme, `credential.helper` vide, HTTP/1.1
2. même fetch en URL explicite
3. **nœud officiel seulement** : SHA via `api.github.com` + tarball `codeload.github.com` (overlay, chemins protégés exclus)

Un clone personnel n’applique **pas** le tarball (ça écraserait le travail local).

## Commandes

```bash
# machine déjà clonée
bash scripts/artcb_follow_main.sh

# installer le timer (déjà appelé par install.sh)
bash scripts/install_follow_main.sh

# opérateur : poser le timer sur les 4 VM + mesurer
PYTHONPATH=src python3 scripts/artcb_sync_official_nodes.py --install
```

## Fusion `main`

`gh` est en lecture seule ici. La fusion GitHub se fait par `git push origin HEAD:main` si la protection le permet, ou par merge de la PR dans l’UI. **PR #51 (rescue OVH2) ne doit pas entrer dans `main`.**

## Interdits

- wipe `blocks.jsonl`
- `install.sh` / genesis / `init-node` comme méthode de redeploy
- rescue OpenStack
- `certified_distributed_mainnet=true`
- imprimer un token / PEM
