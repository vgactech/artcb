# Rapport 199 — `main` fusionné et 4 nœuds redéployés (livre conservé)

**Horodatage :** 2026-09-02T15:00:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false` × 4, non modifié)  
**Branche de travail :** `cursor/merge-main-redeploy-16d8`  
**`main` (branche officielle GitHub) :** `f8118ffea00b1cad5cb3396e29c923b379f6c815`

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **`main`** | La branche officielle GitHub du dépôt `vgactech/artcb`. C’est la référence que l’opérateur a demandé de remplir. |
| **Redéployer** | Remplacer le **code** sur les 4 VMs déjà existantes (`git fetch` / checkout / `systemctl restart artcb`). **Pas** recréer le disque, **pas** `install.sh`, **pas** vider `blocks.jsonl`. |
| **Livre** | La chaîne locale `data/chain/blocks.jsonl`. Ici : height **1**, hash `b8a7d5ef…bfce`. |
| **AND** | Les **DEUX** signatures (Ed25519 **et** ML-DSA-65). Visible sur `/health` via `pqc.hybrid_and_function`. |
| **Keep-book** | Même schéma que les sims 190/191 : checkout du SHA voulu, `/etc/artcb/release.env`, restart. Genèse et wallets intacts. |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 8 | OVH1 HTTP 200, SHA **avant** `30a7696a45888133b04e0ff78bbff2a9473c102f`, branche `cursor/dv01-tpm-wpp-chaos-16d8`, token non affiché |
| Fetch `origin/main` | 15 | `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` (stale vs live) |
| Fusion D-045 + HW + AND | 40 | 198 contient déjà D-045 + 192 + 196. Merge `origin/main` + `origin/cursor/hybrid-and-call-sites-198-16d8`. Conflits : `AUTO_PROMPT_ARTCB`, `scripts/replit_git_sync.sh` |
| Docs 195 + 197 | 50 | Rapports cherry-pick, **pas** de secrets. `IONOS_EMAIL=` reste commenté |
| pytest ciblé | 65 | **102 passed** (191, 196, 198, 190, 174, libp2p, p2p API, 188, symbol P2P, 178) |
| Push `main` | 75 | `git push origin cursor/merge-main-redeploy-16d8:main` → `aeb132a..f8118ff` **OK** |
| Deploy OVH1 + AWS3 | 85 | `git fetch origin main` + reset + restart. SHA `f8118ff…` |
| Deploy OVH2 + OVH4 | 92 | HTTPS GitHub **refusé** (pas d’identifiants) → **bundle git** keep-book, même SHA |
| Vérif 4 nœuds | 100 | Health 200 × 4, même SHA, même `last_hash`, AND visible, certif **false** |

## SHA avant / après (mesurés, pas inventés)

| | Avant (live D-045) | Après (nouveau `main`) |
|--|--------------------|------------------------|
| `git_sha` × 4 | `30a7696a45888133b04e0ff78bbff2a9473c102f` | `f8118ffea00b1cad5cb3396e29c923b379f6c815` |
| `git_branch` × 4 | `cursor/dv01-tpm-wpp-chaos-16d8` | `main` |
| `last_hash` × 4 | `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce` | **identique** |
| height × 4 | 1 | 1 |
| protocol | `189-mainnet-1` | `189-mainnet-1` |
| network_id | `artcb-mainnet-1` | `artcb-mainnet-1` |
| certified | **false** | **false** |
| `tpm_device_present` | false | false |
| `tpm_type` | absent du `/health` (code 191) | **`absent`** (code 196) |
| AND sur `/health` | champs absents | `hybrid_and_function=verify_hybrid_and`, `hybrid_and_call_sites_wired=true`, `hybrid_verify_mode=AND` |
| `blocks.jsonl` | 1 ligne | 1 ligne (`wc -l` remote) |

`origin/main` **avant** push : `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5`.  
`origin/main` **après** push : `f8118ffea00b1cad5cb3396e29c923b379f6c815`.

Ce rapport est un commit **docs** postérieur au SHA live. Les nœuds restent sur `f8118ff…` (le code déployé). Pas de 2ᵉ redeploy pour un markdown.

## Ce qui a été fusionné dans `main`

Ordre réel (ancêtres, pas 12 branches au hasard) :

1. `origin/main` (`aeb132ae`) — runtime Replit 179/181 conservé.
2. D-045 `origin/cursor/dv01-tpm-wpp-chaos-16d8` — **ancêtre** de 198.
3. HW A–E : `origin/cursor/hybrid-and-hw-196-16d8` **plus complet** que `ovh3-baremetal-hw-16d8` (196 = 192 + preuve AND).
4. AND call sites : `origin/cursor/hybrid-and-call-sites-198-16d8` (PR #48).
5. Docs : `rapports/195_audit_live_matrix_2026-09-01.md` + `rapports/197_ionos_login_hint_2026-09-02.md` (AUTO_PROMPT déjà annexé dans 198).

Conflits résolus :

- `AUTO_PROMPT_ARTCB` : **les deux** (179/181 **et** 188–198).
- `replit_git_sync.sh` : `ARTCB_REPLIT_SNAPSHOT_ONLY` (autoscale, **pas** d’`unshallow` au boot) + `fetch --unshallow` seulement si un `.git` existe. Interdit `fetch --depth 1 origin` (test e2e190).

`OPERATOR_MAINNET_CERTIFICATION_GO` reste **False**. Aucune URL Replit compte en dur dans `config.py` (`BOOTSTRAP_NODES` = 4 IP).

## Tests (avant push `main`)

```
PYTHONPATH=src python3 -m pytest \
  tests/test_e2e191_d045.py tests/test_e2e196_hybrid_and_hw.py \
  tests/test_e2e198_hybrid_and_call_sites.py tests/test_e2e190_mainnet_validate.py \
  tests/test_e2e174_dv_3node.py tests/test_libp2p_p2p.py tests/test_p2p_api.py \
  tests/test_e2e188_live_bft.py tests/test_symbol_p2p_integration.py \
  tests/test_e2e178_replit_adversarial.py -q
```

**102 passed.** Première passe : `replit_git_sync` (shallow fetch) corrigé ; `libartcb_chain.so` compilé localement (non commité).

## Déploiement keep-book

Méthode (OVH1 `152.228.144.34`, AWS3 `51.44.222.232`) :

- SSH : `~/.ssh/artcb_ovh_deploy` + `deploy/ovh_artcb_node_1.known_hosts` (OVH1) ; clé AWS3 dédiée.
- `git fetch origin main` → `checkout -B main origin/main` → `reset --hard origin/main`
- `/etc/artcb/release.env` (`ARTCB_GIT_SHA` + `ARTCB_GIT_BRANCH`)
- `sudo systemctl restart artcb`
- **Non exécuté :** `install.sh`, `scripts/init_genesis.py`, init-node / wallet Replit, vidage `blocks.jsonl`.

OVH2 `151.80.107.29` et OVH4 `91.134.45.8` : `git fetch origin main` → `fatal: could not read Username for 'https://github.com'` (HTTPS sans identifiants, **pas** un wipe). Contournement : bundle `30a7696a..f8118ff` scp’d, `git fetch` du bundle, même `release.env` + restart. HEAD = `f8118ff…`. Leur `origin/main` **tracking** reste stale (75 / 68 commits d’écart annoncé par git) ; `/health.git_sha` est la vérité.

Premier essai OVH2/OVH4 : rc 128 **avant** checkout → nœuds restés sur `30a7696a`. Restore GitHub aussi en 128 (même cause). Livre intact. 2ᵉ essai bundle : **OK**.

## Matrice live après (mesurée)

Tous : health **200**, PQC **ML-DSA-65**, `high_value_hybrid_enforced=false`, mutations P2P **401** (DELETE peers / POST sync / POST gossip).

| Nœud | IP | mesh (3 autres IP) | `tpm_type` |
|------|-----|--------------------|------------|
| OVH1 | 152.228.144.34 | 151.80.107.29, 51.44.222.232, 91.134.45.8 | absent |
| OVH2 | 151.80.107.29 | 152.228.144.34, 51.44.222.232, 91.134.45.8 | absent |
| AWS3 | 51.44.222.232 | 151.80.107.29, 152.228.144.34, 91.134.45.8 | absent |
| OVH4 | 91.134.45.8 | 151.80.107.29, 152.228.144.34, 51.44.222.232 | absent |

`mesh_missing=[]` × 4. `tpm_device_present=false`, `attestation_available=false` × 4.

## Interdits respectés

- Pas d’`install.sh` / `init_genesis.py` / wipe `chain.key`
- Pas de reset genèse / `blocks.jsonl`
- Pas d’init-node / wallet Replit
- Pas de checkout OVH 258100013 / bare metal
- Pas de tokens affichés
- Pas de `OPERATOR_MAINNET_CERTIFICATION_GO=true` / `certified=true`
- Pas d’URL Replit compte en dur dans `config.py`

## Outils absents

`ManagePullRequest` absent. Push **direct** `main` autorisé par l’opérateur et **réussi**. PR #48 (base `main`, `CONFLICTING` avant merge) : commits 198 sont dans `main` via le merge 199.

## Dette (pas un échec live)

OVH2 et OVH4 ne peuvent pas `git fetch` GitHub en HTTPS sans identifiants. Prochains deploys : bundle, ou remote SSH, ou credential **nœud** (jamais coller un token dans git).
