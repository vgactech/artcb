# Rapport 195 — Matrice live 4 nœuds (soir 2026-09-01), audit expert STALE

**Horodatage mesures :** HTTP `2026-09-01T22:59:00Z` · Replit `2026-09-01T22:59:43Z` · SSH lecture seule dans la même minute  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false` × 4 sur `/health`)  
**Nœud canonique bootstrap :** `https://152.228.144.34:8443` — clé présente, **token non affiché**  
**Branche de ce rapport :** `cursor/audit-live-matrix-195-16d8` (créée depuis `origin/main`)  
**Interdit respecté :** pas de `install.sh` / `init_genesis` / init-node Replit / déploiement `origin/main` / TX nouvelle / URL Replit recollée dans `config.py`

L’audit expert recollé (branche `cursor/replit-sync-ready-16d8` SHA `a82eb91fc2fbf16cd1d934e841fa8a27cc64d789`, DV PENDING/BLOCKED, `live_bft=false`, `ovh1_redeployed` inconnu) décrit **un état plus ancien**. Ce fichier est une **mesure neuve**. Il n’écrase pas les rapports 191–194 (absents de `origin/main` ; ils vivent sur d’autres branches).

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **SHA / `git_sha`** | Empreinte du commit (40 caractères hex) **vraiment servi** par le nœud. Mesurée sur `/health`, jamais inventée. |
| **`protocol_version`** | Version du **réseau** que le nœud déclare (`189-mainnet-1` ce soir sur les 4 VMs). |
| **`network_id`** | Nom du réseau (`artcb-mainnet-1`). Un Replit encore en shim n’est **pas** sur ce réseau. |
| **`genesis_hash`** | Identifiant déclaré de la genèse (`genesis-artcb-mainnet-1`). Ce n’est pas le hash du bloc 0. |
| **height / `last_hash`** | Nombre de blocs publics et empreinte du **dernier** bloc. 4 nœuds homogènes = même height + même `last_hash`. |
| **BFT** | Vote à **majorité** des nœuds (ici N=4, F=1, Q=3 : 3 voix sur 4). Portée **settlement** prepare/commit, **pas** l’ajout de bloc PBFT. |
| **`live_bft_implemented`** | Le moteur BFT HTTP existe et répond. `true` ce soir × 4. |
| **PQC** | Crypto post-quantique. `pqc.available=true` + algo `ML-DSA-65` sur les 4 VMs. |
| **`hybrid_verify_mode`** | Vérification **AND** : Ed25519 **et** ML-DSA doivent passer. Présent dans `pqc.policy` / `crypto_policy`. |
| **TPM / `/dev/tpm0`** | Puce physique anti-fraude. Le fichier Linux n’existe **que** si la puce (ou un vTPM) est là. |
| **`hardware_assurance_level`** | Note A–E du matériel. **Absent** de `/health` sur le SHA live `30a7696` (le champ n’est pas encore exposé). |
| **`bootstrap_mode`** | `true` = nœud d’affichage **sans** wallet / sans miner. `false` sur les 4 VMs. |
| **`certified_distributed_mainnet`** | Drapeau opérateur « mainnet certifié ». **false** × 4. Homogénéité ≠ certification. |
| **`release_integrity`** | Contrôle d’intégrité du binaire/release. `ok` × 4. |
| **Announce / annuaire** | Un clone dit « me voici ». On ne lit que les URL **déjà** dans `GET /api/v1/network/nodes` → `announced`. |
| **`ovh1_redeployed`** | Ancienne inconnue : « OVH1 a-t-il le même code que les autres ? ». Tranchée par le SHA mesuré. |

## Avancement (cette mission)

| Étape | % | Résultat |
|-------|---|----------|
| 1. Bootstrap live | 15 | HTTP 200, SHA `30a7696a45888133b04e0ff78bbff2a9473c102f`, branche `cursor/dv01-tpm-wpp-chaos-16d8`, token non imprimé |
| 2. HTTP 4 nœuds (health + p2p + chain + nodes + consensus) | 45 | 200 HTTP **et** HTTPS × 4 ; matrice unique ci-dessous |
| 3. SSH lecture seule TPM / DMI | 60 | `/dev/tpm0` **absent** × 4 ; vendor OpenStack Nova / Amazon EC2 ; **aucun redémarrage** |
| 4. Replit **déjà annoncé** | 75 | 2 URL d’annuaire sondées ; shim `replit_shim` ; **pas** de wallet ; **pas** recollées dans git |
| 5. Contre-audit (preuves) | 90 | 189-mainnet-1 · BFT live · 4 hash égaux · OVH1 = tip D-045 · secrets OVH1 encore partagés (registre seulement) |
| 6. Git + poussée | 100 | branche poussée ; PR via compare si collaborator indisponible |
| 7. TX DV-04 | — | **Non jouée** (les 4 sont déjà homogènes ; risque livre inutile) |

**Total livrable matrice + rapport : 100 %.** Certification : **0 %** (verrou inchangé).

## Git : live ≠ `origin/main` (pas de déploiement)

| Ref | SHA (empreinte) | Note |
|-----|-----------------|------|
| `/health` live × 4 | `30a7696a45888133b04e0ff78bbff2a9473c102f` | message : `fix(191): never bake Replit hostnames; clones auto-announce` — **code D-045** |
| Tip docs D-045 `origin/cursor/dv01-tpm-wpp-chaos-16d8` | `454a1f61a231f74751072cd81a5017f3b1471a29` | +1 commit docs(191) **après** le code live |
| `origin/main` (fetch 2026-09-01 soir) | `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` | `Fix reproducible runtime installation` |
| Audit stale | `a82eb91fc2fbf16cd1d934e841fa8a27cc64d789` | `cursor/replit-sync-ready-16d8` — **ancêtre** de `30a7696`, pas l’état servi |

`30a7696` et `origin/main` **ne sont pas** sur la même lignée (ni l’un ancêtre de l’autre). **Aucun** `git checkout origin/main` sur les VMs.

## Matrice unique — 4 seeds (mesurée, pas inventée)

Sources : `GET /health` + `GET /api/v1/p2p/status` + `GET /api/v1/chain/status` + `GET /api/v1/consensus/status` + `GET /api/v1/network/nodes` en HTTP `:8000` et HTTPS `:8443` (même SHA HTTPS = HTTP). SSH : `test -e /dev/tpm0` + `/sys/class/dmi/id/*`.

| Champ | OVH1 `152.228.144.34` | OVH2 `151.80.107.29` | AWS3 `51.44.222.232` | OVH4 `91.134.45.8` |
|-------|----------------------|----------------------|----------------------|---------------------|
| `/health` HTTP / HTTPS | 200 / 200 | 200 / 200 | 200 / 200 | 200 / 200 |
| **SHA** | `30a7696a45888133b04e0ff78bbff2a9473c102f` | **identique** | **identique** | **identique** |
| **branch** | `cursor/dv01-tpm-wpp-chaos-16d8` | **identique** | **identique** | **identique** |
| **protocol_version** | `189-mainnet-1` | **identique** | **identique** | **identique** |
| **network_id** | `artcb-mainnet-1` | **identique** | **identique** | **identique** |
| **genesis_hash** | `genesis-artcb-mainnet-1` | **identique** | **identique** | **identique** |
| **height** | **1** | **1** | **1** | **1** |
| **last_hash** | `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce` | **identique** | **identique** | **identique** |
| `last_timestamp` | `2026-09-01T18:34:30Z` | **identique** | **identique** | **identique** |
| `chain_valid` | true | true | true | true |
| `public_state_digest` | `99ccbf3d81f5568ab3d5097b318d4a3d3f0639efdb24f9cd71899065e38129bb` | **identique** | **identique** | **identique** |
| **pqc.available** | true | true | true | true |
| pqc.algorithm | ML-DSA-65 | ML-DSA-65 | ML-DSA-65 | ML-DSA-65 |
| **hybrid_verify_mode** | **AND** | **AND** | **AND** | **AND** |
| `crypto_suite` (p2p) | `hybrid:ed25519+ML-DSA-65` | **identique** | **identique** | **identique** |
| **bootstrap_mode** | false | false | false | false |
| **certified_distributed_mainnet** | **false** | **false** | **false** | **false** |
| **tpm_device_present** (`/health`) | false | false | false | false |
| SSH `/dev/tpm0` | **no** | **no** | **no** | **no** |
| **hardware_assurance_level** (`/health`) | **ABSENT** | **ABSENT** | **ABSENT** | **ABSENT** |
| **release_integrity** | ok | ok | ok | ok |
| `live_bft_implemented` | **true** | **true** | **true** | **true** |
| BFT N / F / Q | 4 / 1 / 3 | 4 / 1 / 3 | 4 / 1 / 3 | 4 / 1 / 3 |
| BFT protocol | `188-live-bft-prepare-commit` | **identique** | **identique** | **identique** |
| DMI vendor / produit | OpenStack Foundation / OpenStack Nova | OpenStack Foundation / OpenStack Nova | Amazon EC2 / t3.small | OpenStack Foundation / OpenStack Nova |
| hostname | `artcb-node-1` | `node-artcb-ovh-2` | `ip-172-31-8-93` | `node-artcb-ovh-4` |
| `device_fingerprint_prefix` | `a6fce8a864ecee5c` | `e03586f358a76215` | `19d8fde2f7a78d09` | `224af0ed024f7070` |
| `cloud_provider` | ovh | ovh | aws | ovh |
| seeds annuaire | 4 IP seulement | 4 IP seulement | 4 IP seulement | 4 IP seulement |
| `peer_count` (p2p) | 7 | 10 | 12 | 10 |

Les 4 `device_fingerprint_prefix` sont **distincts** (4 machines, pas un clone de disque recopié).  
`hardware_assurance_level` **n’existe pas** dans `public_machine_view` du SHA `30a7696`. Les faits SSH (VM OpenStack / EC2, pas de `/dev/tpm0`) correspondent à un niveau logiciel **E** si on applique le barème plus tardif (rapports 192+) — **on ne l’invente pas sur `/health`**.  
`peer_count` différent = restes dans `peers.json` (dont éventuellement `169.254.169.254` encore sur disque, masqués par l’API). Ça ne casse **pas** l’égalité des hash.

### Seeds dans l’annuaire (pas Replit)

Les 4 nœuds déclarent exactement :

```
http://152.228.144.34:8000
http://151.80.107.29:8000
http://51.44.222.232:8000
http://91.134.45.8:8000
```

BFT `compatible_remote_hosts` : chaque nœud voit les **3 autres** IP (mesh 4).

## Replit — seulement les URL déjà dans `announced`

**Pas** recollées dans `config.py`. **Pas** de wallet. **Pas** d’init-node.

Cache d’annuaire OVH1 (`source=seed_probe`, `updated_at` 19:29–20:15Z — **stale** par rapport à 22:59Z) :

| URL déjà listée | Cache annuaire | Mesure 22:59:43Z |
|-----------------|----------------|------------------|
| `https://artcb--vgacofficiel.replit.app` | `git_sha=99e83b9996aee66666d2c45107aaae8e78339c6b`, `network_id=artcb-devnet-1`, `bootstrap_mode=true`, `online=true` | `/health` 200 **`phase=replit_shim`** — `git_sha=null`, `bootstrap_mode=null`, message *Shim only — not FastAPI /health* ; `/api/v1/network/nodes` **404** ; chain/p2p **404** |
| `https://artcb--vgac42371.replit.app` | `git_sha=null`, `bootstrap_mode=false`, `online=true` | idem shim + 404 API |

Ce soir les deux clones **ne servent plus** le FastAPI bootstrap mesuré dans le rapport 191 (`174-devnet-1` / `99e83b`). Ils servent un **shim de démarrage**. Ce n’est **pas** une preuve PQC, **pas** un nœud mainnet, **pas** un wallet.

Republish Autoscale (hors scope) pour qu’ils voient `30a7696` et s’annoncent tout seuls. Le protocole ne doit **pas** contenir ces hostnames.

## Audit stale vs ce soir — preuves

| Affirmation de l’audit recollé | État **mesuré** 2026-09-01 22:59Z | Preuve |
|-------------------------------|-----------------------------------|--------|
| Branche / SHA `replit-sync-ready` `a82eb91` | Les 4 VMs servent `30a7696` (`dv01-tpm-wpp-chaos`) | `/health` × 4 |
| Réseau encore `174-devnet-1` | **`189-mainnet-1`** / `artcb-mainnet-1` / `genesis-artcb-mainnet-1` × 4 | `/health` + p2p |
| `live_bft=false` | **`live_bft_implemented=true`** × 4 ; N=4 F=1 Q=3 ; proto `188-live-bft-prepare-commit` | `/api/v1/consensus/status` |
| DV PENDING/BLOCKED comme vérité actuelle | Homogénéité **DV-04** : 4 `last_hash` égaux ; BFT endpoint live (DV-05 moteur). Flood D-045 **déjà** joué le même jour (rapport 191, SHA **identique**) : 64×4 `/health` 200 + netem OVH4 restauré. **Cette mission n’a pas rejoué le flood.** | chain + consensus + 191 |
| « jamais 4 hash égaux » | height **1** hash `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce` **× 4** | `/api/v1/chain/status` |
| `ovh1_redeployed` inconnu / bloquant | **Tranché.** OVH1 SHA = tip **code** D-045 `30a7696` = OVH2 = AWS3 = OVH4 | `/health` OVH1 |
| Code `a82eb91` : `LIVE_BFT_IMPLEMENTED=False`, `artcb-devnet-1` | Vrai **pour ce commit git** ; **faux** pour les processus live | `git show a82eb91:src/artcb/consensus_spec.py` vs HTTP live |

### Ce qui **reste vrai** (pas stale)

- `certified_distributed_mainnet=false` — le verrou opérateur n’a pas bougé.
- TPM absent sur les 4 VMs — dit honnêtement, pas inventé.
- Isolation secrets **OVH1 encore partagée** : dans `node_registry` du SHA live `30a7696`, `ovh-node-1.doppler_project = artcb-blockchain` (projet **partagé**) ; note publique : coffre dédié `artcb-ovh-node-1` **jamais créé**. OVH2 / AWS3 / OVH4 ont chacun leur projet (`artcb-2` / `artcb3` / `artcb-4`). **Aucun secret listé, aucun token affiché.**
- Replit **sans** wallet / **sans** init-node.
- `origin/main` ≠ SHA live → ne pas déployer `main` sur OVH.
- Architecture PIN = SHA git, pas une preuve TPM.

## Pourquoi pas de TX DV-04

Les 4 nœuds sont **déjà** homogènes (même height, même `last_hash`, même digest). Une TX de plus changerait le livre pour un test déjà PASS (D-043/D-044/D-045). **Aucun** script existant n’a été lancé. La matrice suffit.

## Interdits — journal

| Action | Fait ? |
|--------|--------|
| Afficher un token / une clé | **non** |
| Inventer SHA / solde / bloc / Settlement | **non** |
| `init-node` Replit / créer un wallet Replit | **non** |
| `install.sh` / `init_genesis` / deploy `origin/main` | **non** |
| Recoller une URL Replit dans `config.py` | **non** |
| Redémarrer une VM | **non** |
| Nouvelle TX | **non** |

## Verdict

Les 4 seeds sont un **même livre mainnet** (`189-mainnet-1`, height 1, hash `b8a7d5ef…bfce`), **même code D-045**, **BFT live allumé**, **certif false**. L’audit `a82eb91` / DV PENDING / `live_bft=false` / `ovh1_redeployed` est **périmé**. Replit annoncé = shim, pas un 5ᵉ nœud de consensus.
