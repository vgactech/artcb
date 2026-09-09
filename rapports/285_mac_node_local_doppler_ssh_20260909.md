# Rapport 285 — Déploiement mac-node-local + accès Cursor via Doppler

**Date** : 2026-09-09  
**SHA live** : `60a40cee7f28de291c7476e54602f87bc737d6cb` = `origin/main`  
**Statut service** : `healthy` — PID actif, `launchd` KeepAlive  
**Auteur** : Bob (agent local, session 285)

---

## Contexte

- Dépôt mis à jour depuis `8e95fde` (R284) vers `60a40ce` (+2 fichiers)
- Clef SSH `cursor_agent` révoquée le 2026-09-09 (exposée en chat)
- Mot de passe sudo `amelie92` : **à changer manuellement** (`passwd`)
- Objectif : donner à l'agent Cursor un accès sécurisé à cette machine via Doppler

---

## Ce qui a été fait

### 1. Mise à jour dépôt
```
git pull origin main
# 2696f2e → 8e95fde (387 fichiers, R265–R284)
```

### 2. Enregistrement node `mac-node-local`

**[`src/artcb/node_registry.py`](src/artcb/node_registry.py)**

| Paramètre | Valeur |
|---|---|
| `node_id` | `mac-node-local` |
| `provider` | `local-macos` |
| `doppler_project` | `artcb-1` |
| `doppler_token_env` | `KEY_API_ARTCB_DOPPLER_MAC` |
| `health_http` | `http://10.234.49.2:8001` |
| `ssh_host` | `10.234.49.2` |
| `ssh_user` | `deyi` |

`NODE_SECRET_ALLOWLIST["mac-node-local"]` : `ARTCB_API_KEY`, `ARTCB_PORT`, `ARTCB_KEM_STORAGE_KEY`, `CURSOR_SSH_PUBLIC_KEY`, `CURSOR_SSH_PRIVATE_KEY`, etc.

### 3. Secrets Doppler provisionnés

**Projet `artcb-1` / config `prd`** :

| Secret | Description |
|---|---|
| `ARTCB_NODE_ID` | `mac-node-local` |
| `ARTCB_PORT` | `8001` |
| `ARTCB_HOST` | `0.0.0.0` |
| `ARTCB_NODE_PUBLIC_URL` | `http://10.234.49.2:8001` |
| `ARTCB_NODE_WALLET_ADDRESS` | `artcb1hk6qyqqxywmfkuu2ad2ams9xnf667j7l49cl5h` |
| `ARTCB_KEM_STORAGE_KEY` | 32 bytes hex (généré fresh, Doppler uniquement) |
| `ARTCB_WALLET_PASSPHRASE` | passphrase locale |
| `CURSOR_SSH_PUBLIC_KEY` | clef ed25519 `cursor_mac_node` (pubkey) |
| `CURSOR_SSH_PRIVATE_KEY` | clef privée (secret protégé, jamais affiché) |
| `ARTCB_NODE_SSH_HOST` | `10.234.49.2` |
| `ARTCB_NODE_SSH_USER` | `deyi` |

**Projet `artcb-blockchain` / config `prd`** :

| Secret | Valeur |
|---|---|
| `KEY_API_ARTCB_DOPPLER_MAC` | token service Doppler `artcb-1/prd` (protégé) |

### 4. Nouvelle clef SSH pour Cursor

```
Algo     : ed25519
Fichier  : ~/.ssh/cursor_mac_node
Label    : cursor-agent@mac-node-local
Empreinte: SHA256:5LdOI2m7lL2tJWrsl56gB+n7zrnwmtv9bUI0J5S2CxU
```

- Pubkey dans `~/.ssh/authorized_keys`  
- Clef privée dans Doppler `artcb-1/prd` → `CURSOR_SSH_PRIVATE_KEY`  
- **Jamais** transmise en clair dans ce chat

### 5. Service launchd macOS

**[`deploy/mac_node_local_launchd.plist`](deploy/mac_node_local_launchd.plist)**  
Installé : `~/Library/LaunchAgents/me.artcb.node.plist`

```
Label       : me.artcb.node
Commande    : doppler run --project artcb-1 --config prd -- uvicorn :8001
WorkingDir  : /Users/deyi/.bob/playground
PYTHONPATH  : src
KeepAlive   : true
RunAtLoad   : true
ThrottleInt : 10s
Logs        : logs/api_node_macbookair.log
```

Le token Doppler est lu depuis la **session CLI globale** (`~/.doppler`) — jamais en dur dans le plist.

---

## Mesures live

| Métrique | Valeur |
|---|---|
| **git_sha** | `60a40cee7f28de291c7476e54602f87bc737d6cb` |
| **origin/main** | `60a40cee7f28de291c7476e54602f87bc737d6cb` ✅ |
| **git_branch** | `main` |
| **status** | `healthy` |
| **launchd PID** | 4241+ (KeepAlive actif) |
| **port** | `8001` (0.0.0.0) |
| **TPM** | `absent` (niveau E — logiciel, Darwin attendu) |
| **bootstrap_mode** | `false` |
| **SSH** | `cursor_mac_node` active dans `authorized_keys` |

---

## Instructions pour Cursor

### Récupérer la clef SSH depuis Doppler

```bash
# Cursor dispose déjà de KEY_API_ARTCB_DOPPLER_MAC dans artcb-blockchain
# Pour se connecter à la machine :

PRIVKEY=$(doppler secrets get CURSOR_SSH_PRIVATE_KEY \
  --project artcb-1 --config prd \
  --token $KEY_API_ARTCB_DOPPLER_MAC --plain)

echo "$PRIVKEY" > /tmp/cursor_mac_key
chmod 600 /tmp/cursor_mac_key
ssh -i /tmp/cursor_mac_key deyi@10.234.49.2
```

### Paramètres de connexion

| Paramètre | Valeur |
|---|---|
| **Host** | `10.234.49.2` (LAN — RFC1918, pas joignable depuis cloud) |
| **User** | `deyi` |
| **Port SSH** | `22` |
| **Clef** | `CURSOR_SSH_PRIVATE_KEY` dans Doppler `artcb-1/prd` |
| **Token Doppler** | `KEY_API_ARTCB_DOPPLER_MAC` dans `artcb-blockchain` |
| **ARTCB health** | `http://10.234.49.2:8001/health` |

### Note réseau

`10.234.49.2` est RFC1918 — **injoignable depuis les 4 VMs cloud** sans tunnel.  
Un agent Cursor local (sur ce Mac ou sur le même LAN) peut s'y connecter directement.

---

## Ce qui reste (non revendiqué)

| Item | Statut |
|---|---|
| Tunnel WireGuard/ngrok pour joindre le Mac depuis cloud | NON fait |
| Intégration `mac-node-local` dans les campagnes de certification | NON fait (observateur, pas PBFT officiel) |
| Rotation mot de passe sudo `amelie92` | **À FAIRE MANUELLEMENT** |
| `ARTCB_KEM_STORAGE_KEY` : supprimer le fallback machine_id (warning encore présent) | warning bénin — KEM recréé avec la bonne clef |

---

## Sécurité — état des clefs

| Clef | Statut |
|---|---|
| `cursor_agent` (ancienne) | **RÉVOQUÉE** 2026-09-09, fichiers supprimés |
| `cursor_mac_node` (nouvelle) | Active, dans Doppler uniquement |
| Mot de passe `amelie92` | **À CHANGER** — exposé en session chat |
