# Rapport 193 — Chasse du crédit OVH ~10 € et refus mesuré de commander le bare metal

**Horodatage :** 2026-09-01T22:50:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Branche :** `cursor/ovh3-baremetal-hw-16d8`  
**Décision :** D-047  
**Simu :** `simulations/20260901T224536Z_e2e193_ovh_order` `failures=[]`

## Vocabulaire (chaque terme)

| Terme | Sens simple |
|-------|-------------|
| **Bare metal** | Serveur **physique** loué dans un datacenter (une vraie machine), **pas** une VM OpenStack / Public Cloud. |
| **nic** | Identifiant du **compte** OVH, genre `xy4589-ovh`. Un nic = un client. Ce n’est pas une carte réseau. |
| **SKU** | Modèle tarifé (code catalogue). Ex. `25skb012` = KS-B à 9,99 €/mois. |
| **TPM** | Puce physique anti-fraude. `/dev/tpm0` n’existe **que** si la puce (ou un vTPM) est là. Non inventé ici. |
| **Crédit Public Cloud** | Argent **collé à un projet VM** OVH. Il paie les instances d2-8, pas un serveur dédié Eco/Kimsufi. |
| **ovhAccount / prepaid** | Portefeuille prépayé du nic, utilisable pour les commandes dédiées. Mesuré à **0,00 €** sur les nics connus. |
| **Eco / Kimsufi / KS-B** | Gamme bare metal d’entrée de gamme OVH. |
| **GRA / RBX / SBG** | Datacenters France (Gravelines / Roubaix / Strasbourg). |
| **git_sha live** | Empreinte du code **vraiment** servi par le nœud. Mesurée, pas devinée. |
| **403** | L’API OVH refuse les clés (périmées ou invalides). On continue à chercher ailleurs. |

## Réponse directe à l’utilisateur

**Commande bare metal : NON.**  
Ce n’est **pas** un basculement théorique : le compte qui a le ~10 € a été **trouvé et mesuré**. Ce crédit **ne peut pas** payer un Eco, et le SKU le moins cher est **en rupture**.

| Champ | Valeur mesurée |
|-------|----------------|
| Commande exécutée | **NON** (`checkout` jamais POST) |
| nic du ~10 € | **xy4589-ovh** (OVH4, email `vgac42@gmail.com`) |
| Nature du 10 € | Crédit **Public Cloud** id `263152` « Credit provisionning » = **10,00 € encore dispo** |
| prepaid ovhAccount | **0,00 €** (xy4589 **et** vc491276) |
| SKU le moins cher | `25skb012` KS-B = **9,99 €/mois** TTC catalogue FR |
| Stock KS-B GRA | **unavailable** ; GET checkout **400** `not available in gra` |
| SKU en stock FR | `24sk50-v1` KS-5 = **17,99 €** (1H-low GRA/RBX) — plus cher que 10 € prepaid |
| IP bare metal | **aucune** (slot `ovh-baremetal-1` toujours vide) |
| TPM `/dev/tpm0` | **non** mesuré sur une machine physique (pas de serveur). Sur OVH1 live : **absent** (Nova / niveau E) |
| Carte bancaire | **non débitée** (moyens Eco = carte / SEPA / PayPal, pas le crédit cloud) |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 10 | health 200 ; SHA live `30a7696a45888133b04e0ff78bbff2a9473c102f` ; token non affiché |
| `origin/main` | 15 | `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` ≠ live → **pas de deploy main** |
| Chasse secrets | 40 | Cursor `OVH_*`, Doppler `artcb-blockchain` / `artcb-2` / `artcb3` / `artcb-4`, `~/.artcb/nodes/*`, SSH, nœuds live |
| Mesure nics | 65 | 2 nics authentifiés + OVH1 en 403 ; crédit 10 € identifié |
| Catalogue + panier | 85 | KS-B 9,99 rupture GRA (API + checkout 400) ; KS-5 17,99 en stock |
| Commande | 90 | **refusée** avec preuves HTTP ; carte non débitée |
| Rapport + git | 100 | 193 + D-047 ; certif **false** |

## Chasse credentials (noms seulement, jamais les valeurs)

| Source | Trouvé |
|--------|--------|
| Secrets Cursor `OVH_*` | nic hint process `xy4589-ovh` ; `/me` **403** `This credential does not exist` (clés injectées ≠ Doppler OVH4) |
| `OVH3_APPLICATION_KEY` / `OVH3_*` | **absents** |
| Doppler `artcb-blockchain` (`DOPPLER_TOKEN`) | OVH1 : `/me` **403** sur CK, CK_NEW, CK_EXPIRED. `OVH_SERVER_IP=51.255.22.253` (vieille IP, pas le live) |
| Doppler `artcb-2` | nic **vc491276-ovh** `/me` **200** ; prepaid **0,00 €** ; 0 dédié ; crédit essai 199,80 € Public Cloud |
| Doppler `artcb-4` | nic **xy4589-ovh** `/me` **200** ; prepaid **0,00 €** ; 0 dédié ; **10,00 € Credit provisionning** + essai 199,84 € |
| Doppler `artcb3` (`KEY_API_ARTCB_DOPPLER_3`) | **AWS seulement** — aucun secret OVH. Projet `artcb-3` **n’existe pas** |
| `artcb-baremetal-1` / `artcb-ovh3` | tokens service : **pas d’accès** (400). `DOPPLER_PERSONAL_TOKEN` **absent** |
| `~/.artcb/nodes/` | ovh-2, ovh-4, aws-3 — **pas** de 3ᵉ nic |
| SSH `~/.ssh/artcb*` | commentaires `artcb-ovh-node-2` / `artcb-ovh-node-4` / `artcb-aws-node-3` uniquement |
| OVH1 live `ubuntu@152.228.144.34` | `cursor_agent.env` = clés API ARTCB seulement ; chassis **OpenStack Nova** ; `/dev/tpm0` **absent** |
| OVH2 / OVH4 live | `node_init.env` wallet — **pas** de clés OVH API |

Workplace Doppler visible avec les 4 tokens service : `lvxsecret` — chaque token ne liste **qu’un** projet.

## Preuves API (pas inventées)

### Soldes

| nic | `/me` | prepaid | Crédits cloud mesurés | Dédiés |
|-----|-------|---------|------------------------|--------|
| `xy4589-ovh` | 200 | **0,00 €** | 263152 = **10,00 €** « Credit provisionning » (jusqu’au 2027-09-01) ; 263153 = **199,84 €** « Free Trial Offer » (jusqu’au 2026-09-30) | 0 |
| `vc491276-ovh` | 200 | **0,00 €** | 263140 = 199,80 € essai Public Cloud | 0 |
| OVH1 (Doppler) | **403** | non mesurable | — | — |

Facture xy4589 `FR79913993` du 2026-08-31 : **12,00 €** TTC pour « Cloud Credit Provisionning » 10,00 € HT (commande `257039708`). C’est **le** crédit ~10 €. Il est **déjà** sur le projet Public Cloud `node artcb ovh 4` (la VM 91.134.45.8).

Doc OVH : un crédit Public Cloud ne se transfère pas et ne paie que le projet cloud. Les moyens de paiement Eco mesurés : `creditCard=true`, `bankAccount=true`, `paypal=true` — **pas** ovhAccount, **pas** crédit cloud.

### Catalogue Eco FR (maintenant)

| SKU | Nom | €/mois | Stock mesuré |
|-----|-----|--------|--------------|
| **25skb012** | KS-B Xeon E5-1620v2 | **9,99** | GRA **unavailable** (1 ligne). Panier : GET checkout **400** `25skb012.ram-32g-ecc-1333.noraid-1x120ssd is not available in gra` |
| 25skc012 | KS-C | 11,99 | unavailable |
| 24sk40-v1 / 24sk102 | KS-4 / KS-1 | 16,99 | unavailable |
| **24sk50-v1** | KS-5 | **17,99** | **1H-low** GRA + RBX (plus cher que le prepaid 0 € et que le 10 € cloud) |

Panier dry-run xy4589 : POST `/order/cart` 200, POST `/eco` 25skb012 200, configs GRA acceptées, **GET** checkout 400 rupture. **POST checkout jamais envoyé.** DELETE cart 403 (droit API manquant) — panier orphelin vide de paiement.

## Pourquoi on ne commande pas sur xy4589 malgré le 10 €

1. L’utilisateur a dit « le OVH qui contient le crédit ». Ce nic **est** celui-là.  
2. Mais le **solde prepaid** (celui qui paie un Eco) est **toujours 0,00 €**.  
3. Le 10 € est du **crédit VM**. Commander un KS-B/KS-5 débiterait la **carte** (`XXXXXXXXXXXX2512`). Interdit.  
4. KS-B (seul SKU ≤ 10 €) est **en rupture GRA**.  
5. KS-5 en stock coûte **17,99 €** > 10 €.

## Interdits respectés

- Pas de solde 10 € inventé comme prepaid. Le 10,00 € cloud est **lu** sur `/cloud/project/…/credit/263152`.  
- Pas de TPM inventé. Pas de Settlement inventé. Pas de `git_sha` inventé.  
- Pas de deploy `origin/main`. Pas de `install.sh` / `init_genesis.py` / wipe `chain.key`.  
- Pas d’`init-node` Replit. Pas d’URL Replit en dur.  
- `OPERATOR_MAINNET_CERTIFICATION_GO` reste **false**.  
- Aucun token affiché.

## GO restant (opérateur)

1. Si le 10 € doit acheter un **bare metal** : le verser en **ovhAccount prepaid** (ou créer un 3ᵉ nic + `OVH3_*`) — le crédit cloud actuel **ne suffit pas** juridiquement/API pour Eco.  
2. Attendre le retour en stock de KS-B `25skb012` GRA (ou un SKU ≤ solde prepaid).  
3. Ne pas faire payer la carte OVH4 pour un KS-5 à 17,99 € sans ordre explicite « débiter la carte ».
