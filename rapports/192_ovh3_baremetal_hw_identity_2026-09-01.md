# Rapport 192 — Bare metal OVH3 (crédit non mesuré), identité hardware A–E, audit stale

**Horodatage :** 2026-09-01T22:20:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Branche :** `cursor/ovh3-baremetal-hw-16d8`  
**Décision :** D-046  
**Simu :** `simulations/` e2e192 (après push)

## Vocabulaire (première fois)

| Terme | Sens simple |
|-------|-------------|
| **Bare metal** | Serveur **physique** loué (une vraie machine dans un datacenter), **pas** une VM OpenStack. |
| **TPM** | Puce physique anti-fraude. `/dev/tpm0` = le fichier Linux qui apparaît **seulement** si la puce (ou un vTPM) est là. |
| **vTPM** | Fausse puce créée par l’hyperviseur (logiciel de VM). Ça ressemble à un TPM, ce n’est pas le silicium du serveur. |
| **TEE** | Enclave (SEV / SGX / TDX) : un coffre CPU. On ne le déclare que si `/dev/sev`, `/dev/sgx_enclave` ou `/dev/tdx_guest` existe. |
| **HSM** | Boîtier crypto externe (OKMS, CloudHSM). Uniquement si l’opérateur l’a branché (`ARTCB_HSM_BINDING`). |
| **Niveaux A–E** | A = TPM physique ; B = vTPM ; C = TEE sans TPM ; D = HSM ; E = hash logiciel (machine-id + instance). |
| **nic OVH** | Identifiant de **compte** OVH (`quelquechose-ovh`). Un nic = un client. |
| **SKU Eco / KS-B** | Référence produit Kimsufi (serveur physique d’entrée de gamme). |
| **Seed / carnet** | Les 4 IP toujours allumées dans git. Pas un compte Replit. |
| **Announce** | Un clone dit « me voici » (`POST /api/v1/network/announce`). |
| **CORS** | Quels sites navigateur ont le droit d’appeler l’API. Regex `*.replit.app` / `*.repl.co` / `*.replit.dev`. |
| **Settlement** | Accord de paiement entre nœuds. **Non inventé ici.** |
| **git_sha live** | Empreinte du code **vraiment** servi par le nœud. Mesurée, pas devinée. |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 10 | SHA `30a7696a45888133b04e0ff78bbff2a9473c102f` clé présente, token non affiché |
| `origin/main` | 15 | `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` ≠ live → **pas de déploiement main** |
| Matrice 4 nœuds | 30 | voir tableau ci-dessous |
| Secrets OVH3 | 45 | **absents** |
| Catalogue Eco | 55 | KS-B `25skb012` = **9,99 €/mois** (API publique FR) ; GRA **unavailable** |
| Code A–E + registre | 75 | livré |
| Tests + rapport | 90 | ce fichier |
| PR | 100 | branche poussée, certif **false** |

## Matrice LIVE mesurée (2026-09-01 ~22:10Z)

Ne pas traiter l’audit collé (174-devnet-1, PRE-DV-04, `live_bft_implemented=false`) comme la vérité de ce soir.

| Nœud | IP | SHA | protocol | network | height | last_hash | tpm `/dev/tpm0` | virt | niveau | bootstrap |
|------|----|-----|----------|---------|--------|-----------|-----------------|------|--------|-----------|
| OVH1 | 152.228.144.34 | `30a7696a45888133b04e0ff78bbff2a9473c102f` | 189-mainnet-1 | artcb-mainnet-1 | 1 | `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce` | **no** | kvm / OpenStack Nova | **E** | false |
| OVH2 | 151.80.107.29 | idem | idem | idem | 1 | idem | **no** | kvm / OpenStack Nova | **E** | false |
| AWS3 | 51.44.222.232 | idem | idem | idem | 1 | idem | **no** | amazon / t3.small | **E** | false |
| OVH4 | 91.134.45.8 | idem | idem | idem | 1 | idem | **no** | kvm / OpenStack Nova | **E** | false |

Seeds live = **uniquement** les 4 IP.  
`certified_distributed_mainnet=false` × 4.  
PQC `ML-DSA-65`. 4 `device_fingerprint_prefix` distincts.  
SEV / SGX / Nitro enclaves : **absents** × 4. On n’invente pas NitroTPM.

### Replit annoncé (pas dans le carnet git)

| Clone | `/health` | SHA | protocol | bootstrap |
|-------|-----------|-----|----------|-----------|
| annuaire `artcb--vgacofficiel` | 200 | `99e83b9996aee66666d2c45107aaae8e78339c6b` | **174-devnet-1** | true |
| annuaire `artcb--vgac42371` | 200 | (vide) | (vide) | status `starting` |

Ces hostnames viennent de **leur** announce / reste d’annuaire, **pas** de `BOOTSTRAP_NODES`. Republish pour qu’ils voient `30a7696`. Interdit : `init-node` / wallet Replit.

## Audit collé : ce qui est FAUX ce soir / ce qui RESTE vrai

**Faux (stale, pré-D-042…D-045) :**

- `live_bft_implemented=false` — le code live a `LIVE_BFT_IMPLEMENTED=True` (D-042, e2e188).
- Réseau `174-devnet-1` comme vérité des 4 seeds — les 4 VMs sont sur `artcb-mainnet-1` / `189-mainnet-1` (D-043).
- DV-04 « jamais 4 hash égaux » — height 1 hash `b8a7d5ef…bfce` **égal × 4** (déjà D-043/D-044).
- BFT / chaos « absents » — D-042 BFT, D-045 flood 64×4 + netem OVH4 restauré.
- `ovh1_redeployed` comme blocage actuel — OVH1 est sur le même SHA `30a7696` que les 3 autres.

**Encore vrai :**

- Architecture A : PIN = SHA git, pas une preuve TPM.
- Replit **sans** wallet / **sans** init-node.
- Isolation secrets OVH1 : token live encore sur Doppler **partagé** `artcb-blockchain` (coffre `artcb-ovh-node-1` jamais créé).
- `169.254.169.254` **stale** encore dans `peers.json` disque des 4 nœuds. L’API liste le **cache** désormais (plus affiché). On n’a **pas** réécrit le fichier live.

## OVH3 / commande bare metal — mesuré, pas inventé

### Clés cherchées

| Source | Trouvé |
|--------|--------|
| Secrets Cursor `OVH_*` | nic **xy4589-ovh** (OVH4). `/me` process env → **403** `NOT_CREDENTIAL` (clés périmées dans l’injection). |
| Doppler `artcb-blockchain` | clés OVH1 → **403** `INVALID_CREDENTIAL` |
| Doppler `artcb-2` + `KEY_API_ARTCB_DOPPLER_2` | nic **vc491276-ovh** — solde ovhAccount **0,00 €** ; 0 serveur dédié |
| Doppler `artcb-4` + `KEY_API_ARTCB_DOPPLER_4` | nic **xy4589-ovh** — solde **0,00 €** ; 0 serveur dédié |
| `KEY_API_ARTCB_DOPPLER_3` | projet **`artcb3` = AWS**, pas un nic OVH |
| Projet Doppler `artcb-3` | **n’existe pas** |
| `~/.artcb/nodes/` | `ovh-node-2.env`, `ovh-node-4.env`, `aws-node-3.env` — **pas** ovh-3 / baremetal |
| `DOPPLER_PERSONAL_TOKEN` | **absent** (pas de création `artcb-baremetal-1`) |
| `OVH3_APPLICATION_KEY` / `OVH3_APPLICATION_SECRET` / `OVH3_CONSUMER_KEY` / `OVH3_NIC` | **absents** |

Le crédit « ~10 € » **n’a pas pu être lu**. Il n’est **pas** reporté comme 10,00 €.

### Prix catalogue (API publique, sans commande)

| SKU | Nom | € / mois | Stock GRA (mesuré) |
|-----|-----|----------|--------------------|
| **25skb012** | KS-B Intel Xeon E5-1620v2 | **9,99** | **unavailable** |
| 25skc012 | KS-C E5-1650v2 | 11,99 | unavailable |
| 24sk40-v1 | KS-4 | 16,99 | unavailable |
| 24sk50-v1 | KS-5 | 17,99 | 1H-low (plus cher que ~10 €) |

**Commande : NON.** Motifs cumulés : clés OVH3 absentes ; solde OVH3 non mesuré ; nics connus à 0,00 € (on ne les dépense pas) ; SKU le moins cher en rupture.

Quand les clés arriveront : `OVH3_APPLICATION_KEY` + `OVH3_APPLICATION_SECRET` + `OVH3_CONSUMER_KEY` + `OVH3_NIC` (un nic **nouveau**, pas vc491276 / xy4589). Puis `python3 scripts/ovh_baremetal_quote.py` (et `--order` seulement si crédit ≥ prix **et** stock). Installer le nœud **sans** `install.sh` / **sans** vider `blocks.jsonl`. `node_id` = `ovh-baremetal-1`. Doppler dédié `artcb-baremetal-1` + `KEY_API_ARTCB_DOPPLER_BAREMETAL`.

## Avant / après (fichiers)

| Fichier | Avant | Après |
|---------|-------|--------|
| `hardware_identity.py` | TPM present/absent + binding cloud | Niveaux **A–E**, virt/TEE/HSM/PCR honnêtes |
| `public_machine_view()` | pas de `hardware_assurance_level` | level / kind / chassis_virtual / tee_detected |
| `node_registry.py` | 4 clouds + replit | + **`ovh-baremetal-1`** (IP vide, en attente) |
| CORS | regex déjà là (D-045) | constante `REPLIT_CORS_ORIGIN_REGEX` |
| `GET /p2p/peers` | montrait 169.254 | cache `stale_link_local_hidden` |
| Quote | — | `scripts/ovh_baremetal_quote.py` |
| Tests | 191 | **192** nouveau |

## Interdits respectés

- Pas de TPM inventé. Pas de solde 10 € inventé. Pas de Settlement inventé.
- Pas de déploiement `origin/main`. Pas de `install.sh` / `init_genesis.py` live.
- Pas de `init-node` Replit. Pas d’URL compte Replit en dur.
- `OPERATOR_MAINNET_CERTIFICATION_GO` reste **false**.
- Aucun token affiché.

## GO restant (opérateur)

1. Créer l’app API du **3ᵉ nic** et coller `OVH3_*` (Cursor + Doppler dédié).
2. Relancer le quote : si crédit mesuré ≥ 9,99 **et** KS-B de retour en stock → alors seulement commander.
3. Brancher `ovh-baremetal-1` en 5ᵉ machine de **test** hardware (annoncer son IP, ne pas réécrire la genèse).
