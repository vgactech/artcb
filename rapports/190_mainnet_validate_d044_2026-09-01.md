# Rapport 190 — D-044 validation mainnet, P2P durci, Replit sans wallet

**Horodatage :** 2026-09-01T18:50:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Simu :** `simulations/20260901T184857Z_e2e190_mainnet_validate/` (`failures=[]`)  
**SHA live 4 nœuds :** `fe369bdf28c160f17169f99dd919ddcc4440dce6`  
**PR :** https://github.com/vgactech/artcb/pull/46

## GO

L’opérateur **valide définitivement** D-043 (V-01…V-07 + genèse `artcb-mainnet-1`) et demande la suite : tests unitaires, intégration, stress réel, audit Replit. **Pas de wallet / pas d’init-node** sur Replit.

## Avant / après

| Surface | Avant | Après (mesuré) |
|---------|-------|----------------|
| `release.py` PIN | égalité exacte → `pin_mismatch` | ancêtre Git = `ok` (fast-forward) |
| `replit_git_sync.sh` | `fetch --depth 1` | `--unshallow` ; PIN non journalisé |
| `POST/DELETE /p2p/peers` | public | **401** sans Bearer |
| `register-public` 169.254 | accepté (stale encore en liste) | **400** `link_local_or_reserved_forbidden` |
| `GET /api/v1/network/nodes` | absent | **200** sans wallet |
| Replit URL registre | `artcb--vgac42.replit.app` | `artcb--vgacofficiel.replit.app` |
| Livre mainnet | height 1 `b8a7d5ef…` | **inchangé** (pas vidé) |

## Preuves live e2e190

- 4 nœuds : `artcb-mainnet-1` / `189-mainnet-1` / height 1 / même `last_hash` `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce`
- HTTP+HTTPS `/health` 200 ; `release_integrity=ok`
- Visibilité réciproque des **4 IPs infra** : `missing_infra_ips=[]` partout
- DELETE sans auth → 401 ; SSRF metadata → 400
- 16 GET `/health` concurrents × 4 nœuds = 200
- Timeout `192.0.2.1` → http 0
- `install.sh` / `init_genesis.py` / init-node / flood paquetaire : **non exécutés**

## Replit production (mesuré, pas inventé)

URL : `https://artcb--vgacofficiel.replit.app`

| Champ | Valeur |
|-------|--------|
| `/live` | 200 bootstrap |
| `bootstrap_mode` | true |
| `network_id` | `artcb-devnet-1` (**pas** mainnet) |
| `protocol_version` | `174-devnet-1` |
| `git_sha` | `99e83b9996aee66666d2c45107aaae8e78339c6b` |
| `release_integrity` | ok |
| `/api/v1/p2p/status` | 503 |
| `/api/v1/network/nodes` | 503 (code 174, pas encore cette branche) |

Aucun wallet créé. Replit **ne détecte pas** les 4 nœuds P2P — c’est le mode bootstrap voulu. L’annuaire sans wallet arrivera quand Autoscale pointera cette branche.

## Tests

Unitaires + intégration : `tests/test_e2e190_mainnet_validate.py` (PIN ancêtre, SSRF, 401, flood local 48× `/health`).  
Stress **réel borné** live : 16 GET parallèles / nœud, timeout, SSRF, 401.  
**Pas** de flood SYN/partition sur le livre mainnet (DV-02 C reste PARTIAL).

## Verdicts

DV-01 PASS · DV-02 **PARTIAL** · DV-03 PASS · DV-04 PASS · DV-05 PASS · DV-06 **PARTIAL** · DV-07 PASS.

`certified_distributed_mainnet` **false**.
