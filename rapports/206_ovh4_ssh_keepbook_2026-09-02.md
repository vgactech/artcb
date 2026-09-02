# Rapport 206 — OVH4 SSH sans rescue + keep-book `origin/main`

**Horodatage :** 2026-09-02T20:22:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Branche PR :** `cursor/ovh4-ssh-keepbook-568e`

Le badge Cursor `KEY_API_ARTCB_DOPPLER_4` était collé. Rien n’est inventé : SHA, hauteur, HTTP sont mesurés. PEM / `dp.st.…` / mots de passe **non imprimés**.

## 1. Coffre `artcb-4`

| Check | Mesure |
|-------|--------|
| `KEY_API_ARTCB_DOPPLER_4` | présent (len 53, préfixe `dp.st.`) |
| Doppler `GET …/secrets/names?project=artcb-4&config=dev` | HTTP 200 |
| `SSH_PRIVATE_KEY` au départ | **absent** |
| Clés OVH (`OVH_APPLICATION_*`) | présentes ; `GET https://eu.api.ovh.com/1.0/me` → nic **`xy4589-ovh`** HTTP 200 |
| `OVH_*` du process Cursor | non utilisées (nœud 1) |

## 2. Instance (API xy4589, pas rescue)

- id `22dc6a47-5b79-4084-82d7-eabb4f5b2680` `node-artcb-ovh-4` GRA11 d2-8 **ACTIVE** IPv4 `91.134.45.8`
- Health avant keep-book : SHA `f28418084d84e00d3d5290ceefb846b30af527de` branche `cursor/artcb-me-official-16d8` HTTP 200
- `POST /cloud/project/…/instance/…/vnc` → novnc (instance **running**, pas rescue)
- Nova `changePassword` → action `compute_set_admin_password` **Success** (qemu-ga). Console tty1 : user **`root`** (pas `ubuntu`). Root **relocké** (`passwd -l`) après SSH ubuntu.

## 3. Porte SSH (sans rescue, sans PEM utilisateur)

1. Nouvelle paire ed25519 `artcb-ovh-node-4-20260902` ; privée POST Doppler `artcb-4` / `dev` / `SSH_PRIVATE_KEY` (HTTP 200).
2. Publique git `deploy/artcb_ovh_node_4.pub` fingerprint **`SHA256:ZAGMFcZMNUR1g3iPAen187zVl0ImPRArzTghs1blC5k`**.
3. Publique ajoutée dans `/home/ubuntu/.ssh/authorized_keys` via VNC tty1 **root** (`tee -a`), pas de disque rescue, pas de `reinstall`.
4. `ssh ubuntu@91.134.45.8` → **SSH_OK** `hostname=node-artcb-ovh-4` `grep -c artcb-ovh-node-4-20260902` = 1.

## 4. Keep-book `origin/main`

`git fetch origin main` sur la VM : `could not read Username for 'https://github.com'` (HTTPS sans identifiants, **pas un wipe**). Bundle local `ad017bca` → `git fetch` du bundle → `checkout -B main` → `reset --hard`.

| | Avant | Après |
|--|-------|-------|
| `git_sha` | `f28418084d84e00d3d5290ceefb846b30af527de` | **`ad017bca05c2e3799c7dcd120ca1797968d499b6`** |
| `git_branch` | `cursor/artcb-me-official-16d8` | **`main`** |
| `data/chain/blocks.jsonl` | 1 ligne | **1 ligne** (non vidé) |
| `install.sh` / genesis / init-node | — | **non exécutés** |
| rescue | — | **non** (`/mnt/rescue` absent) |

Live mesuré après restart `artcb` :

- `http://91.134.45.8:8000/health` 200 `git_sha=ad017bca…` `git_branch=main`
- `https://91.134.45.8:8443/health` 200 même SHA
- `https://n4.artcb.me/health` **200** (nginx + Let’s Encrypt HTTP-01 `n4.artcb.me`, CERTBOT_RC=0). HTTP :80 → 301
- chaîne : height **1**, `last_hash` `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce`, `chain_valid=true`
- OVH1 `http://152.228.144.34:8000/health` inchangé `ad017bca…` `main` (pas redéployé ici)

`origin/main` local agent = `ad017bca05c2e3799c7dcd120ca1797968d499b6` = live OVH1 = live OVH4.

## 5. Interdits respectés

- Pas de rescue OVH4.
- Pas de wipe `blocks.jsonl`.
- Pas de `certified_distributed_mainnet=true`.
- Pas de déploiement `main` commandé sur OVH1 au-delà de l’état déjà keep-book.
- Token / PEM / mot de passe console non affichés.

## 6. Reste hors cette PR

OVH2 SSH keep-book (Doppler `artcb-2` PEM / autre porte) n’est **pas** traité ici. Bench 4 nœuds D-053 campagne distribuée toujours bloquée tant que n2 n’est pas keep-book.
