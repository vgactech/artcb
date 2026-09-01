# Rapport 189 — gel V-01…V-07 et genèse live `artcb-mainnet-1`

**Horodatage :** 2026-09-01T18:35:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Simu :** `simulations/20260901T183347Z_e2e189_mainnet_genesis/`  
**SHA déployé :** `ad4687d16be55fb82114f38e70687156c0ed4567`  
**Branche :** `cursor/mainnet-genesis-d043-16d8`  
**PR :** https://github.com/vgactech/artcb/pull/45

## Phrase GO utilisée (langue à répéter)

> GO D-043 : tu valides toi-même, tu figes V-01…V-07 et les autres locks encore ouverts, tu me notifies les choix, puis tu mets le mainnet ARTCB en ligne.

## Choix figés et pourquoi

| ID | Choix final | Pourquoi (culture projet, pas une invention) |
|----|-------------|-----------------------------------------------|
| V-01 | **A** — snapshot au début d’epoch | Déjà `EpochCoordinator` + sim 167 |
| V-02 | Effet transfert = **epoch suivant** | Un transfert mid-epoch ne réécrit pas P(N) |
| V-03 | Grâce **24 h** live / 1 s sim | `DEFAULT_GRACE_SECONDS = 86400` |
| V-04 | Retrait = **prochain snapshot** | Même file que V-02 |
| V-05 | Finalité économique **N=2** | Distinct du BFT settlement DV-05 **Q=3** |
| V-06 | `DemographicReference` **modèle B** | D-025 ; Q-E03 extrait ONU WPP daté **reste ouvert** |
| V-07 | HBP **10→60→20** ancres **0 / 4.15e9 / 8.30e9** | `hbp.py` live ; pas de réécriture ratio non simulée |
| D-032 | Fenêtre Ed25519 jusqu’au **2026-12-31** | Ne pas fermer trop tôt |
| Faucet | **403** | D-017 tARTCB = testnet |
| Certif | **false** | DV-02 C flood/chaos **non joué** |

## Avant / après

| Surface | Avant (mesuré) | Après (mesuré) |
|---------|----------------|----------------|
| `src/artcb/crypto_policy.py` `NETWORK_ID` | `artcb-devnet-1` | `artcb-mainnet-1` |
| `PROTOCOL_VERSION` | `174-devnet-1` | `189-mainnet-1` |
| `GENESIS_HASH` (identifiant déclaré) | `genesis-artcb-v2` | `genesis-artcb-mainnet-1` |
| `ECONOMIC_V_LOCKED` | `False` | `True` |
| Live 4 nœuds `git_sha` | `7cf8c37a85f19aa57c2c012c955657635f37b54f` | `ad4687d16be55fb82114f38e70687156c0ed4567` |
| Live height / `last_hash` | 8 / `a749b3b7…c5b543d1` (sondes 174) | **1** / `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce` |
| `public_state_digest` | `cd65c004…ea33ba7d` | `99ccbf3d81f5568ab3d5097b318d4a3d3f0639efdb24f9cd71899065e38129bb` |
| Faucet POST | HTTP 200 | HTTP **403** `faucet_disabled_on_mainnet` |
| `certified_distributed_mainnet` | false | **false** |

Livre 174 conservé : `data/chain/blocks.jsonl.bak-d043-testbook` (60400 octets) sur les 4 VMs.  
`data/chain.key` **conservé** (85 octets ; dates 19–31 août). `install.sh` et `init_genesis.py` **non exécutés**.

Fausse alerte sim : `*_chain_key_missing` — le script testait `data/chain/chain.key`. Chemin réel = `data/chain.key`. Sonde corrective : `20_chain_key_probe.json`. Les 4 nœuds ont signé le bloc 0 avec la clé existante (`chain_valid=true`).

## Scénarios e2e189 (mesurés)

- STOP les 4 services → checkout `ad4687d` → vidage `blocks.jsonl` + `incoming_public.jsonl` **avant** tout start
- height 0 puis TX publique OVH2 `store_http=200` index 0 hash `b8a7d5ef…`
- sync 200 sur 4 nœuds ; 4 `last_hash` égaux après TX **et** après restart OVH1
- TPM : `TPM_DEV=no` sur les 4 (DV-01 C = identité crypto maintenant, TPM *when available*)
- Hybride AND + fenêtre 2026-12-31 → DV-07 **PASS**

## Verdicts DV (pas une certif globale)

| ID | Statut | Commentaire |
|----|--------|-------------|
| DV-01 | PASS | cartes signées ; TPM absent |
| DV-02 | PARTIAL | HTTP/HTTPS/register OK ; flood/chaos **non fait** |
| DV-03 | PASS | 4 nœuds `artcb-mainnet-1` / `189-mainnet-1` / `genesis-artcb-mainnet-1` |
| DV-04 | PASS | 4 tips égaux après TX + restart |
| DV-05 | PASS | inchangé e2e188 (scope settlement, pas PBFT `append_block`) |
| DV-06 | PARTIAL | restart OK ; packet-loss chaos non fait |
| DV-07 | PASS | D-032 B + D-034 A en vigueur |

## Ce qui reste pour une certification

1. DV-02 C flood / partition / chaos sur **testnet autorisé** (pas casser le livre mainnet)
2. DV-06 packet-loss si on veut le C
3. Q-E03 extrait ONU WPP 18+ daté (V-06 modèle B déjà gelé)
4. Attestation TPM plus tard pour prod critique
5. Replit Autoscale **reste en pause**
6. `append_block` n’est **pas** du PBFT

L’identité **mainnet est en ligne**. La **certification distribuée** ne l’est pas. Ne pas confondre les deux.
