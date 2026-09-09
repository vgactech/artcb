# Rapport 286 — Cursor cloud → mac-node-local (Doppler + SSH)

**Date** : 2026-09-09  
**Agent** : Cursor cloud (`bc-1563f881-5a04-45df-9d2a-24e83164568e`)  
**origin/main / OVH1 live SHA** : `75836c715fb47cf87d37365bd6d5b8e36d940c5e`  
**Livre OVH1** : height **1133**, last_index **1132**, tip `cc0bf8a1053c7ae75c3c00b0a4ebf72da311efbf1f13e3164a95f159fc7d71b3`  
**CERTIFIED_100** : false  
**N04** : last, FAIL (non rejoué ici)

Ne pas inventer un `git_sha` health Mac. Ne pas afficher de token Doppler ni de clef SSH.

---

## Consigne

R285 a demandé à Cursor :

```bash
PRIVKEY=$(doppler secrets get CURSOR_SSH_PRIVATE_KEY \
  --project artcb-1 --config prd \
  --token $KEY_API_ARTCB_DOPPLER_MAC --plain)
echo "$PRIVKEY" > /tmp/cursor_mac && chmod 600 /tmp/cursor_mac
ssh -i /tmp/cursor_mac deyi@10.234.49.2
```

## Mesures (cet agent cloud)

| Chemin | Verdict | Preuve |
|--------|---------|--------|
| `KEY_API_ARTCB_DOPPLER_MAC` dans l’env Cursor | **FAIL** | absent ; `_2`/`_3`/`_4` présents (len 53 chacun) |
| `DOPPLER_TOKEN` → `artcb-blockchain`/`dev` | **FAIL** pour le token MAC | 67 noms ; `KEY_API_ARTCB_DOPPLER_MAC` **absent** ; `CURSOR_SSH_PRIVATE_KEY` **absent** |
| `DOPPLER_TOKEN` → `artcb-blockchain`/`prd` | **FAIL** | HTTP 400 « This token does not have access to requested config 'prd' » |
| `DOPPLER_TOKEN` / `_2` / `_3` / `_4` → `artcb-1` | **FAIL** | HTTP 400 projet `artcb-1` non autorisé |
| TCP `10.234.49.2:22` | **NOT_REACHABLE** | `TimeoutError` 5.01 s |
| TCP `10.234.49.2:8001` | **NOT_REACHABLE** | `TimeoutError` 5.01 s |
| SSH login | **FAIL** | pas de PEM écrit (`KEY_API_ARTCB_DOPPLER_MAC` absent) ; LAN timeout de toute façon |
| Health SHA Mac | **non mesuré** | interdit d’inventer |
| `mac-node-local` ∈ `OFFICIAL_COMPUTE_NODE_IDS` | false | observateur uniquement |

Ingest de ce tour : HTTP 409 equivocation (attendu). Prompt hash `5865dc346f73b43ffa010eababea1bffdc8df009e86a69f9ec78f042a319ed03`.

## Écart R285 vs réalité Cursor cloud

R285 a poussé `KEY_API_ARTCB_DOPPLER_MAC` dans **`artcb-blockchain` / `prd`**.  
Le `DOPPLER_TOKEN` des agents Cursor cloud est un service token **`artcb-blockchain` / `dev`**.

Les nœuds 2/3/4 marchent parce que `KEY_API_ARTCB_DOPPLER_2/3/4` sont des **secrets d’environnement Cursor** injectés dans la VM — pas parce qu’ils sont dans Doppler `prd`.

## Correctifs code (ce SHA)

- `NodeSpec.doppler_config = "prd"` pour `mac-node-local` (défaut `dev` était faux).
- Probe fail-closed `src/artcb/mac_node_access.py` + `scripts/run_live286_mac_ssh.py` : jamais de PEM dans le JSON.
- Tests `tests/test_e2e286_mac_ssh.py` (hors OFFICIAL_COMPUTE, RFC1918, pas de SHA inventé).

## Ce que l’humain doit poser pour qu’un agent cloud SSH

1. Secret Cursor d’environnement **`KEY_API_ARTCB_DOPPLER_MAC`** (même geste que `_2`/`_3`/`_4`).
2. Dupliquer le **nom** `KEY_API_ARTCB_DOPPLER_MAC` dans `artcb-blockchain` / **`dev`** si on veut le lire via `DOPPLER_TOKEN`.
3. Tunnel (WireGuard / Tailscale / ngrok **depuis le Mac**) : sinon RFC1918 reste `NOT_REACHABLE`.

## Non revendiqué / non recasté

- Login SSH Mac : **non**.
- Health Mac `75836c7` : **non mesuré par cet agent**.
- Tunnel : **non**.
- Mac dans le quorum PBFT : **non** (et ne doit pas l’être).
- PRE_R273 K1→Node2 GAP : conservé.
- N04 50 % : FAIL last.
- `CERTIFIED_100=false`.
