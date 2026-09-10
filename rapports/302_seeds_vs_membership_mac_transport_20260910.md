# 302 — seeds IPv4 ≠ membership PBFT ; Mac transport NON PROUVÉ

**2026-09-10T11:33:20Z.** `CERTIFIED_100=false`. `includes_thinking=false`. Ingest ce tour : HTTP **409** `equivocation` — le prompt **n’est pas** on-chain.

**Expertises :** consensus PBFT (membership vs seeds), transport RFC1918, isolation Doppler, gouvernance agents Cursor.

## Accord avec l’audit opérateur

L’audit GitHub est **retenu** :

- `origin/main` du run agent = `e58dc2809495b0352174ed9db34efae2ee728e90` (R301b), après `bc0a9b9` / R300 `c24f097` / `4fe76dd`.
- Thinking privé 100 % local : **non garanti**. Thinking surfacé + journal processus : **mécanismes installés**. Jamais ARTCB.
- `artcb-read-all.mdc` `alwaysApply: true` : correction architecturale.
- Mac `pbft_replica=true` + `official_pbft_replica_ids()` + `primary_of(view)` adaptatif : **oui dans le code**.
- N=5, f=1, Q=3 (Q inchangé vs N=4) : **oui**.
- Ne **pas** lever `CERTIFIED_100`.
- Ne **pas** ajouter le Mac à `OFFICIAL_COMPUTE_NODE_IDS`.
- Health 200 ≠ replica PBFT certifié.
- Run Everything (Unsandboxed) = réglage **Cursor IDE**, pas GitHub, pas identité de consensus.
- R301b documentation : **PASS**. Présence Doppler : mesurée **nom seulement** (voir ci-dessous).

## Mesures live (pas inventées)

| Cible | HTTP `/health` | `git_sha` | height (tip-attest) | last_hash | tip `node_id` |
|-------|----------------|-----------|---------------------|-----------|----------------|
| ovh-node-1 | 200 | `e58dc28…` | 1133 | `cc0bf8a1…` | `ovh-node-1` |
| ovh-node-2 | 200 | `e58dc28…` | 1133 | `cc0bf8a1…` | `ovh-node-2` |
| aws-node-3 | 200 | `bc0a9b9…` ≠ origin/main | 1133 | `cc0bf8a1…` | `aws-node-3` |
| ovh-node-4 | 200 | `e58dc28…` | 1133 | `cc0bf8a1…` | `ovh-node-4` |
| Mac `:8001` | 200 | `e58dc28…` | **6** | `01a5f743…` | wallet `artcb1hk6…` ≠ `mac-node-local` |

- `n_f_q` live = `[5, 1, 3]` ; historique `n_f_q(4)` = `[4, 1, 3]`.
- Mac dans membership : **true**. Mac dans seeds : **false**. Mac dans HTTP reachable (sans tunnel) : **false**.
- `replica_peer_allowed("10.234.49.2")` = **false**.
- Tunnel : `rfc1918_requires_tunnel`, `select_cloud_remote_ok=false`.
- Mac → seeds : `/api/v1/consensus/status` **200** + `tip-attest` **200**. Ce n’est **pas** PREPARE/COMMIT. Champ `not_pbft_prepare_commit=true`.
- Doppler `artcb-1`/`prd` : nom `MAC_SUDO_PASSWORD` **présent** (`name_count=22`, `plain_invoked=false`). Le token env partagé `DOPPLER_TOKEN` (coffre `artcb-blockchain`) est **Invalid Auth** sur `artcb-1` — le probe live retire ce token et utilise le CLI Mac. Jamais `--plain`. Jamais la valeur ici.
- Bootstrap OVH1 : height **1133**, tip `cc0bf8a1…`, `chain_valid=true`, `ai_memory_count=5`, dernier mémo index **1131** graph `ai_memo_fab25419c633` GET 200.
- pytest : **13 passed**.

Log : `logs/302_mac_n5_transport_20260910T113320Z.json`.

## Avant / après (lignes exactes)

### `scripts/run_live270_pbft_cert_matrix.py`

**Avant :** `"n_f_q": list(n_f_q(4)),`

**Après :**

```python
        # ~~n_f_q(4)~~ 2026-09-10T11:20:00Z — formule historique N=4, pas la membership live.
        "n_f_q_historical_four": list(n_f_q(4)),
        "n_f_q": list(official_pbft_n_f_q()),
        "official_pbft_replica_ids": list(official_pbft_replica_ids()),
        "official_compute_seeds": list(OFFICIAL_COMPUTE_NODE_IDS),
        "http_fanout": list(OFFICIAL_COMPUTE_NODE_IDS),
```

Même motif dans `scripts/run_live271_close_not_proven.py`. Les boucles HTTP restent les **4 seeds**.

### `src/artcb/consensus/pbft_exclusive.py`

**Avant :** `hosts = official_http_map()` puis `hosts[primary]` (KeyError si `primary_of(view)==mac-node-local`).

**Après :** `hosts = pbft_reachable_http_map()` ; si primary absent et ce nœud n’est pas le primary → `reason="primary_unreachable_transport"`.

`official_http_map()` reste la carte **seeds** (commentaire barré 2026-09-10T11:20:00Z).

### `src/artcb/node_registry.py`

**Ajout après** `on_official_compute()` (l.203+) : `seed_http_map()`, `_mac_public_tunnel_http()`, `pbft_reachable_http_map()`, `pbft_membership_vs_transport()`. Rien d’effacé. Mac jamais ajouté à `OFFICIAL_COMPUTE_NODE_IDS`.

### `tests/test_e2e273_identity_binding.py` — `test_official_ids_still_four`

**Avant :** seeds == 4 + `primary_of(15)`.

**Après :** docstring historique ; `MAC_NODE_ID in official_pbft_replica_ids()` ; Mac **absent** des seeds ; `len(ids) >= 5`.

### `src/artcb/p2p/official_replica.py`

Docstring recollée (syntaxe cassée par une fermeture `"""` trop tôt). Phrase « four official nodes » **barrée** : seeds IPv4, pas membership. `replica_peer_allowed` inchangé (loopback + `OFFICIAL_COMPUTE_IPV4` seulement).

## Ce qui n’est pas certifié

1. Mac n’a **pas** le livre officiel (6 vs 1133) — **ne pas wipe**.
2. Identité tip-attest Mac ≠ `mac-node-local`.
3. Pas de tunnel public mesuré → les 4 VM ne peuvent pas dial le Mac en P2P officiel.
4. Pas de PREPARE/COMMIT/view-change avec le Mac dans le quorum.
5. AWS3 code SHA en retard (`bc0a9b9`) au moment du probe.
6. `CERTIFIED_100=false`. N04 last FAIL **indépendant**.

## Avancement

Code + tests R302 : **100 %** de la correction d’ambiguïté N=4 dans 270/271 + fail-closed exclusive.  
Preuve Mac replica PBFT live N=5 : **0 %** (mesurée absente, pas « à faire plus tard » sans chiffre).
