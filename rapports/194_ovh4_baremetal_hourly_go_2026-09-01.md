# Rapport 194 — Eco OVH4 : intervalle mesuré (mensuel) + STOP anti-double-commande

**Horodatage :** 2026-09-01T22:57:08Z (commande OVH `2026-09-02T00:57:08+02:00`)  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Branche :** `cursor/ovh4-baremetal-hourly-go-16d8`  
**Décisions :** D-048 (GO carte, un seul checkout) + **D-049** (mesure horaire vs mensuel, order déjà passé)  
**Nœud live canonique :** `https://152.228.144.34:8443` SHA `30a7696a45888133b04e0ff78bbff2a9473c102f` ≠ `origin/main` `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` → **pas de déploiement main**

Cet agent (**GO horaire**) **n’a pas** rappelé `--order`. Un autre agent (GO carte) avait déjà validé le panier.

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **Horaire** | Facturé **chaque heure** (`intervalUnit=hour`). |
| **Mensuel** | Facturé **chaque mois** (`intervalUnit=month`). |
| **Bare metal** | Serveur **physique**, pas une VM OpenStack. |
| **ovhAccount prépayé** | Solde du compte OVH. **Ce n’est pas** le crédit Public Cloud 10 €. |
| **1H-low** | Indicateur de **stock / délai de livraison** (~1 heure), **pas** un tarif horaire. |
| **nic** | Compte OVH (`xy4589-ovh` = OVH4). |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 10 | SHA `30a7696`, clé présente, token non affiché |
| Auth OVH4 | 25 | `~/.artcb/nodes/ovh-node-4.env` → `GET /me` **200** nic **xy4589-ovh** |
| `GET /dedicated/server` **avant** tout `--order` | 40 | **HTTP 200, `[]`** — 0 machine physique listée |
| Paniers / commandes | 55 | 3 paniers (2 dry-run 193 KS-B, 0 checkout). Puis **1 checkout Eco déjà passé** |
| Catalogue Eco : intervalle réel | 70 | **99/99 plans `intervalUnit=month`**, **0 `hour`**. Catalogue dedicated/baremetalServers : 0 `hour` |
| `--order` de cet agent | 85 | **NON exécuté** (anti-double-commande) |
| Rapport + registre | 100 | `ovh-baremetal-1` sans IP ; VM `91.134.45.8` intacte |

## Preuve : l’opérateur croyait « horaire » — l’API dit « mensuel »

### Catalogue public Eco FR (`GET /order/catalog/public/eco?ovhSubsidiary=FR`)

Unités de renouvellement **mesurées** (pas supposées) :

```json
{
  "catalog": "eco",
  "subsidiary": "FR",
  "plan_count": 99,
  "renew_interval_units": {"month": 295},
  "hourly_plan_count": 0,
  "monthly_plan_count": 99,
  "hourly_exists": false,
  "billing": "month_only"
}
```

Échantillon KS-B `25skb012` (extrait `pricings` renew) :

```json
{
  "interval": 1,
  "intervalUnit": "month",
  "capacities": ["renew"],
  "price_eur": 9.99,
  "description": "rental for 1 month"
}
```

Échantillon KS-5 `24sk50-v1` :

```json
{
  "interval": 1,
  "intervalUnit": "month",
  "capacities": ["renew"],
  "price_eur": 17.99,
  "description": "rental for 1 month"
}
```

Aucune ligne `intervalUnit=hour` sur les 99 SKU Eco. Le catalogue `baremetalServers` public FR : **0** pricing `hour` (500 `none` + 500 `month`).

D’où venait « horaire » :

1. Commande Public Cloud `258082826` — *« Consommation à l'heure pour les instances d2-8 gra11 »* = **VM** `91.134.45.8`, pas un dédié.
2. Disponibilité Eco `1H-low` = stock / livraison, **pas** un tarif à l’heure.

**Tender Eco ≠ crédit Public Cloud 10 €.** ovhAccount mesuré : **0,00 €**.

## STOP — checkout Eco déjà passé (ne pas recommander)

| Champ | Valeur mesurée |
|-------|----------------|
| **orderId** | **258100013** |
| HTTP `GET /me/order/258100013` | **200** |
| HTTP `GET /me/order/258100013/status` | **200** `"checking"` |
| Date | `2026-09-02T00:57:08+02:00` |
| SKU | KS-5 `24sk50-v1` Intel Xeon-E3 1270 v6 |
| Datacenter | **rbx** |
| Durée sur chaque ligne | **« 1 mois »** (mensuel) |
| HT / TVA / TTC | **44,98 €** / **9,00 €** / **53,98 €** |
| Détail HT | install KS-5 17,99 € + location 1 mois 17,99 € + 3× HDD 4 To 9,00 € |
| `paymentType` | `debtAccount` (pas un 2ᵉ checkout) |
| followUp | `VALIDATING` / **`FRAUD_MANUAL_REVIEW`** |
| `GET /dedicated/server` après | **200, `[]`** — pas encore livré (revue fraude) |

Phrase opérateur : **Go horaire donné, commande déjà passée par l’agent carte, orderId 258100013, statut checking, revue fraude manuelle, aucun second serveur.**

Paniers restants (non validés, **pas** des commandes) : `artcb-193-preview` et `artcb-193-eco-dryrun` (KS-B `25skb012`, `duration=P1M`).

## VM OVH4 — intacte

- IPv4 **91.134.45.8** inchangée.
- **Pas** de `install.sh`, **pas** d’`init_genesis`, **pas** de déploiement `origin/main`.
- **Pas** d’URL Replit en dur.
- `ovh-baremetal-1` : `ssh_host=null` — on n’invente pas d’IP ni de TPM tant que `/dedicated/server` est vide.

## Interdits respectés

- Tarif / solde / SHA : uniquement des valeurs API ou bootstrap.
- Token jamais affiché.
- Nic interdit `vc491276-ovh` non utilisé.
- Un seul serveur : le checkout existant ; **cet agent n’a pas** POST `/order/cart/.../checkout`.
- Si un futur checkout refusait : codes HTTP dans le rapport, pas de serveur fantôme. Ici le refus n’a pas eu lieu — la commande existe déjà (`checking`).
