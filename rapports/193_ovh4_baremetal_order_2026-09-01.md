# Rapport 193 — Commande Eco OVH4 (nic xy4589-ovh) : refus mesuré

**Horodatage :** 2026-09-01T22:45:00Z  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Branche :** `cursor/ovh4-baremetal-order-e867`  
**Décision :** D-047  
**Nœud live canonique :** `https://152.228.144.34:8443` SHA `30a7696a45888133b04e0ff78bbff2a9473c102f` ≠ `origin/main` `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` → **pas de déploiement main**

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **Bare metal** | Serveur **physique** (machine dans un datacenter), **pas** une VM OpenStack. |
| **nic** | Identifiant de **compte** OVH (`xy4589-ovh` = OVH4). |
| **SKU** | Modèle / référence produit (ex. KS-B `25skb012`). |
| **TPM** | Puce `/dev/tpm0`. Absente sur la VM OVH4 ; **non sondée** sur un dédié jamais livré. |
| **ovhAccount** | Compte prépayé OVH (seul moyen mesuré pour payer un Eco). |
| **Crédit Public Cloud** | Avoir collé au projet cloud (VM d2-8). **Ne paie pas** un Kimsufi / Eco. |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 10 | SHA `30a7696` clé présente, token non affiché |
| Auth API OVH4 | 25 | Doppler `artcb-4` + `~/.artcb/nodes/ovh-node-4.env` → `/me` **200** nic **xy4589-ovh** (vgac42@gmail.com). Env Cursor `OVH_*` → **403** `This credential does not exist` |
| GET `/dedicated/server` **avant** `--order` | 40 | **HTTP 200, `[]`** — 0 serveur physique, rien en livraison |
| Solde mesuré | 55 | ovhAccount **0,00 €** ; crédit cloud **10,00 €** + essai **199,84 €** (pas de tender Eco) |
| Catalogue Eco | 70 | KS-B `25skb012` = **9,99 €** GRA **unavailable** ; moins cher en stock = KS-5 `24sk50-v1` **17,99 €** |
| `--order` | 85 | **NON exécuté** (solde prépayé < prix **et** SKU 9,99 € en rupture) |
| Registre + TPM + PR | 100 | `ovh-baremetal-1` sans IP ; `/dev/tpm0` absent sur 91.134.45.8 (VM gardée) |

## Preuves HTTP / JSON (aucun secret)

### Identité

| Appel | HTTP | Corps public |
|-------|------|----------------|
| `GET /me` (Doppler artcb-4 / env local) | 200 | `nichandle=xy4589-ovh` `email=vgac42@gmail.com` `state=complete` |
| `GET /me` (process `OVH_*` Cursor) | **403** | `class=Client::Forbidden` `message=This credential does not exist` |
| `GET /cloud/project` | 200 | `926bb1d6755e4f2c98ae9db06ef44e4f` (« node artcb ovh 4 ») |
| `GET /cloud/project/…/instance` | 200 | `node-artcb-ovh-4` id `22dc6a47-5b79-4084-82d7-eabb4f5b2680` GRA11 **ACTIVE** IPv4 **91.134.45.8** |

### Inventaire dédié (anti double-commande)

```json
{
  "path": "/dedicated/server",
  "http": 200,
  "servers": [],
  "count": 0
}
```

`GET /dedicated/housing` → 200, `[]`.  
`GET /order/cart` → 200, 1 panier **vide** (expire 2026-09-03, 0 item Eco).  
`GET /me/order` → 4 commandes, **aucune** Eco / Kimsufi : projet Public Cloud, vRack, conso d2-8.

### Soldes — mesurés, pas inventés

| Source | HTTP | Valeur |
|--------|------|--------|
| `GET /me/ovhAccount` + détail | 200 | **0,00 €** (`text=0.00 €`, `value=0`, `availableAfterCredit=0.00 €`) |
| `GET /me/debtAccount` | 200 | `dueAmount=0.00 €` |
| `GET /me/credit/balance` | 200 | liste vide |
| `GET /cloud/project/…/credit/263152` | 200 | **Credit provisionning 10,00 €** dispo (expire 2027-09-01) |
| `GET /cloud/project/…/credit/263153` | 200 | **Free Trial Offer 199,84 €** / 200,00 € (0,16 € déjà utilisés) |
| `GET /me/deposit/PA_FR34236559` | 200 | dépôt **12,00 € TTC** le 2026-08-31 (10,00 € HT → crédit cloud) |
| `GET /me/bill/FR79913993` | 200 | 12,00 € TTC / 10,00 € HT |

Le « ~10 € » de l’opérateur est le **crédit Public Cloud 263152**, confirmé par la commande `257039708` (« Cloud Credit Provisionning » 10,00 €).  
La conso d2-8 GRA11 a déjà prélevé **0,16 €** sur l’essai gratuit (commande `258082826`, statut `delivering`).

**Tender Eco = ovhAccount seulement = 0,00 €.** On ne paie pas un serveur physique avec un avoir VM.

### Catalogue Eco public FR (relire 2026-09-01 ~22:40Z)

| SKU | Nom | € / mois | Stock mesuré |
|-----|-----|----------|--------------|
| **25skb012** | KS-B Xeon E5-1620v2 | **9,99** | GRA **unavailable** |
| 25skc012 | KS-C E5-1650v2 | 11,99 | GRA unavailable |
| 24sk40-v1 | KS-4 | 16,99 | tous DC unavailable / unknown |
| **24sk50-v1** | KS-5 E3-1270 v6 | **17,99** | **1H-low** gra / rbx / bhs / lon / fra |

Moins cher **AVAILABLE** = KS-5 17,99 €, **strictement supérieur** au prépayé 0,00 € (et au crédit cloud 10,00 €, qui de toute façon n’est pas un tender Eco).

### VM OVH4 — gardée, lecture seule

SSH `ubuntu@91.134.45.8` (`~/.ssh/artcb_ovh_node_4` + `deploy/ovh_artcb_node_4.known_hosts`) :

- hostname `node-artcb-ovh-4`
- `/dev/tpm0` = **absent**
- virt = `kvm` / DMI `OpenStack Nova`
- **Pas** de destroy, **pas** de `install.sh`, **pas** d’`init_genesis`, **pas** de vidage `blocks.jsonl`

`ovh-baremetal-1` : `ssh_host=null` — on n’invente pas d’IP ni de TPM sur une machine non livrée.

## Décision de commande

```
auth OK          : oui (nic xy4589-ovh)
GET dédiés       : []  (pas de double-commande)
solde prépayé    : 0,00 €
SKU ≤ solde      : aucun (9,99 € > 0,00 € ; 17,99 € > 0,00 €)
KS-B disponible  : non
nic interdit     : vc491276-ovh non utilisé
--order          : NON
```

Moyen de paiement présent : `CREDIT_CARD` VALID (label masqué). **Non débité.** Un avoir cloud n’autorise pas un prélèvement carte pour un KS-5 à 17,99 €.

## Interdits respectés

- Solde non inventé (0,00 € prépayé, 10,00 € cloud mesurés à part).
- TPM non inventé ; `certified=false`.
- Pas de déploiement `origin/main`.
- Pas de commande sur `vc491276-ovh`.
- VM `91.134.45.8` intacte.
- Aucun token affiché.

## GO restant (opérateur)

1. Créditer **ovhAccount** (prépayé) ≥ prix du SKU Eco **disponible**, **ou** attendre le retour en stock de KS-B 9,99 € **et** un prépayé ≥ 9,99 €.
2. Relancer `python3 scripts/ovh4_baremetal_order.py --order` (liste `/dedicated/server` d’abord).
3. Alors seulement : IP réelle → `ovh-baremetal-1`, sonde `/dev/tpm0` honnête, Doppler `artcb-baremetal-1`.
