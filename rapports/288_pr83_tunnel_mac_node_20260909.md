# Rapport 288 — Intégration PR#83 R286/R287 + état tunnel mac-node-local

**Date** : 2026-09-09  
**SHA live** : `41109a37de4f342650633882eca229c9299577e4` = `origin/main`  
**Hauteur** : 1133 (inchangée — mac-node-local est observateur, pas PBFT)  
**CERTIFIED_100** : `false`

---

## Ce qui a été intégré (PR #83)

PR `cursor/pbft-r287-mac-tunnel-568e` mergée en fast-forward.

### Corrections

| Problème mesuré (R286/R287) | Correction |
|---|---|
| `10.234.49.2` RFC1918 collé comme URL cloud | `tunnel_required=True` dans `NodeSpec` |
| `select_cloud_remote()` acceptait LAN | Refus explicite `rfc1918_requires_tunnel` |
| P2P `http://10.234.49.2:8001` propagé | `private_or_loopback_forbidden` |
| SHA health Mac inventé | Interdit dans `.mdc` + tests |
| `doppler_config` manquant dans `NodeSpec` | Champ ajouté (`prd` pour mac, `dev` default) |

### Fichiers

| Fichier | Rôle |
|---|---|
| [`src/artcb/node_registry.py`](src/artcb/node_registry.py) | `tunnel_required`, `tunnel_ssh_host`, `doppler_config` dans `NodeSpec` |
| [`src/artcb/mac_node_access.py`](src/artcb/mac_node_access.py) | `select_cloud_remote()`, `MacNodeAccessor` |
| [`.cursor/rules/mac-node-local.mdc`](.cursor/rules/mac-node-local.mdc) | Règle Cursor : RFC1918, tunnel, interdits |
| [`tests/test_e2e286_mac_ssh.py`](tests/test_e2e286_mac_ssh.py) | 4 tests LAN/clef/SHA — 4 PASS |
| [`tests/test_e2e287_mac_tunnel.py`](tests/test_e2e287_mac_tunnel.py) | 2 tests tunnel_required — 2 PASS |
| [`logs/286_mac_ssh_live.json`](logs/286_mac_ssh_live.json) | Probe live R286 (0 endpoint ngrok) |
| [`logs/287_mac_tunnel_live.json`](logs/287_mac_tunnel_live.json) | Probe live R287 |

### Tests

```
tests/test_e2e286_mac_ssh.py   4/4 PASS
tests/test_e2e287_mac_tunnel.py 2/2 PASS
```

---

## État mac-node-local

| Paramètre | Valeur |
|---|---|
| `node_id` | `mac-node-local` |
| `provider` | `local-macos` |
| `tunnel_required` | `true` |
| `tunnel_ssh_host` | `null` — pas de tunnel démarré |
| `health_http` | `http://10.234.49.2:8001` (LAN uniquement) |
| ARTCB service | `healthy`, SHA `41109a3`, launchd PID actif |
| `ARTCB_PORT` | `8001` |
| Doppler | `artcb-1/prd`, 21 secrets provisionnés |
| SSH clef | `cursor_mac_node` (ed25519) dans `authorized_keys` |

---

## Ce qui reste bloquant

### Tunnel — action requise sur le Mac

Le tunnel doit être **démarré sur cette machine** (le Mac). Aucun agent cloud ne peut l'initier.

**Option ngrok** (compte déjà configuré avec `NGROK_AUTHTOKEN` dans Doppler `artcb-blockchain`) :

```bash
# Lancer sur le Mac (terminal ou autre launchd agent)
ngrok tcp 22 --log=stdout
# → url tcp://X.tcp.ngrok.io:NNNNN
```

Puis mettre à jour Doppler :
```bash
doppler secrets set \
  ARTCB_MAC_TUNNEL_SSH_HOST="X.tcp.ngrok.io:NNNNN" \
  --project artcb-1 --config prd
```

**Option Tailscale** (persistant, meilleur) :
```bash
brew install tailscale
sudo tailscaled &
tailscale up
# → IP Tailscale stable (100.x.x.x)
```

### Sécurité

- Mot de passe sudo `amelie92` **exposé en chat** → **changer maintenant** : `passwd`
- `cursor_agent` révoquée ✅
- `cursor_mac_node` active ✅, privée uniquement dans Doppler

---

## Mesures live campagne R287 (`20260909T182620Z`)

| Nœud | Résultat |
|---|---|
| ngrok endpoints | 0 / 0 |
| `select_cloud_remote(10.234.49.2)` | `rfc1918_requires_tunnel` |
| P2P propagation LAN | `private_or_loopback_forbidden` |
| SHA Health Mac inventé | **non** (conforme) |
| `CERTIFIED_100` | `false` |

SHA ×4 = `75836c7` au moment du probe, maintenant `41109a3` = `origin/main`.
