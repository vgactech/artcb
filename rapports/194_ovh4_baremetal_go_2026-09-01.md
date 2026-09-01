# Rapport 194 — GO Eco OVH4 : checkout KS-5 RBX (orderId 258100013)

**Horodatage :** 2026-09-01T22:57:08Z (commande OVH `2026-09-02T00:57:08+02:00`)  
**Certification :** **NOT MAINNET CERTIFIED** (`certified_distributed_mainnet=false`)  
**Branche :** `cursor/ovh4-baremetal-go-3c95`  
**Décisions :** D-048 (GO carte, un seul checkout) ; D-049 (pas de 2ᵉ commande ; Eco = mensuel)  
**Nœud live canonique :** `https://152.228.144.34:8443` SHA `30a7696a45888133b04e0ff78bbff2a9473c102f` ≠ `origin/main` `aeb132ae5266cfb9dfdfa8e7eafd49268b726fe5` → **pas de déploiement main**

## Vocabulaire

| Terme | Sens simple |
|-------|-------------|
| **Bare metal** | Serveur **physique** dans un datacenter, **pas** une VM OpenStack. |
| **nic** | Identifiant de **compte** OVH (`xy4589-ovh` = OVH4). |
| **SKU** | Référence produit (ici KS-5 `24sk50-v1`). |
| **FQN** | Configuration complète (CPU + RAM + disques) réellement en stock. |
| **Prepaid ovhAccount** | Solde du compte OVH. **Seul** tender « classique » d’un Eco. Mesuré **0,00 €**. |
| **Crédit Public Cloud** | Avoir collé au projet cloud (VM d2-8). **Ne paie pas** un Kimsufi / Eco. |
| **CREDIT_CARD** | Moyen de paiement **enregistré** sur le nic (préféré, statut VALID). |
| **TPM** | Puce `/dev/tpm0`. **Non sondée** tant que le dédié n’est pas listé. |
| **1H-low** | Indicateur de **stock / délai** (~1 h), **pas** un tarif à l’heure. |
| **Mensuel** | `intervalUnit=month` : facturé **chaque mois**. |
| **FRAUD_MANUAL_REVIEW** | Revue anti-fraude **manuelle** OVH : la livraison n’a pas commencé. |

## Avancement

| Étape | % | Résultat |
|-------|---|----------|
| Bootstrap live | 10 | SHA `30a7696`, clé présente, token non affiché |
| Auth API OVH4 | 20 | `~/.artcb/nodes/ovh-node-4.env` → `GET /me` **200** nic **xy4589-ovh** |
| `GET /dedicated/server` **avant** checkout | 30 | **HTTP 200, `[]`** — 0 serveur physique, rien en livraison |
| Soldes | 40 | ovhAccount **0,00 €** ; crédit cloud **10 €** (pas un tender Eco) ; carte **CREDIT_CARD VALID** default |
| Catalogue + stock | 55 | KS-B `25skb012` 9,99 € GRA **unavailable**. Disque 0 € du KS-5 **rupture**. Moins cher **FR disponible** = KS-5 + 3×4 To à **26,99 € HT / mois** **RBX** |
| Checkout `--order --go` | 75 | **HTTP 200**, **un seul** serveur, **orderId 258100013** |
| Après commande | 90 | `status=checking` ; followUp **FRAUD_MANUAL_REVIEW** ; `GET /dedicated/server` encore **`[]`** |
| SSH / TPM / registre | 100 | **Pas d’IP** inventée ; `/dev/tpm0` non sondé ; VM `91.134.45.8` intacte ; `certified=false` |

## Décision de commande (re-mesurée, pas réinventée)

```
auth OK                 : oui (nic xy4589-ovh)
GET dédiés avant order  : []  (pas de double-commande)
commandes Eco existantes: 0 au moment du POST checkout
solde prépayé           : 0,00 €
KS-B 25skb012           : unavailable
moins cher FR available : 24sk50-v1 + ram-32g + softraid-3x4000sa @ rbx = 26,99 € HT/mois
opérateur GO            : oui (carte autorisée)
--order --go            : OUI, un checkout
```

Sydney KS-3 `24sk302-syd` 18,99 € était plus cheap **mais hors FR**. Consigne : datacenter FR (GRA/RBX/SBG) **si possible** → **RBX**.

Paniers 193 KS-B (`artcb-193-preview` / `artcb-193-eco-dryrun`) : **non validés** (GET checkout 400, SKU unavailable). **Pas** des commandes.

## Preuve HTTP du checkout (aucun secret)

| Appel | HTTP | Corps public |
|-------|------|----------------|
| `POST /order/cart` | 200 | `description=artcb-194-go` |
| `POST /order/cart/{id}/assign` | 200 | panier lié au nic |
| `POST /order/cart/{id}/eco` planCode `24sk50-v1` P1M | 200 | item Eco |
| options RAM / 3×4 To / 500 Mbps | 200 | addons obligatoires du FQN en stock |
| configuration `dedicated_datacenter=rbx` | 200 | FR |
| `dedicated_os=none_64.en` `region=europe` | 200 | |
| `GET .../checkout` (aperçu) | 200 | prix TTC ci-dessous |
| `POST .../checkout` `autoPayWithPreferredPaymentMethod=true` | **200** | **orderId 258100013** |

**Pas de HTTP 400/402.** Pas de retry.

### Commande mesurée ensuite

| Champ | Valeur API |
|-------|------------|
| **orderId** | **258100013** |
| `GET /me/order/258100013` | **200** |
| Date | `2026-09-02T00:57:08+02:00` |
| SKU | KS-5 `24sk50-v1` Intel Xeon-E3 1270 v6 |
| FQN | `24sk50-v1.ram-32g-ecc-2400.softraid-3x4000sa` |
| Datacenter | **rbx** (Roubaix, FR) |
| **HT / TVA / TTC** | **44,98 € / 9,00 € / 53,98 €** |
| Détail HT | install KS-5 **17,99 €** + 1 mois **17,99 €** + 3× HDD 4 To **9,00 €** |
| Renouvellement | **mensuel** (`1 mois` sur chaque ligne ; catalogue Eco `intervalUnit=month`, 0 plan `hour`) |
| `GET /me/order/.../payment` | `paymentType=debtAccount` le `2026-09-02T00:57:11+02:00` |
| `GET /me/debtAccount` due | **0,00 €** (pas un 402 ; le débit carte n’est pas une ligne d’extrait inventée) |
| `GET /me/order/.../status` | **200** `"checking"` |
| followUp | `VALIDATING` / **`FRAUD_MANUAL_REVIEW`** (2026-09-02T00:57:40+02:00) |
| `GET /dedicated/server` après | **200, `[]`** — **pas livré** |

Phrase opérateur si paiement refusé : *« Go donné, checkout refusé, code HTTP, raison »*.  
Ici : **Go donné, checkout HTTP 200, orderId 258100013, 53,98 € TTC, statut checking, revue fraude manuelle. Aucun serveur listé, aucune IP inventée.**

## Ce qui n’existe pas encore

- **Pas** d’entrée dans `/dedicated/server`.
- **Pas** d’IPv4 dédiée → `ovh-baremetal-1.ssh_host` reste `null`.
- **Pas** de sonde `/dev/tpm0` (on ne sonde pas une machine absente).
- **Pas** d’`install.sh`, **pas** d’`init_genesis`, **pas** de déploiement `origin/main`.
- VM live **91.134.45.8** : hostname `node-artcb-ovh-4` **intacte**.

Tant que `FRAUD_MANUAL_REVIEW` n’est pas levée par OVH, la livraison (`DELIVERING` / `AVAILABLE`) reste `TODO`. Un agent suivant relit `/dedicated/server` : s’il voit une IP réelle, alors SSH + TPM honnête, `certified` toujours false.

## Interdits respectés

- Solde / SHA / TPM / IP : uniquement des valeurs mesurées.
- Token / clés / mot de passe de commande : jamais affichés.
- Nic interdit `vc491276-ovh` non utilisé.
- Un seul checkout Eco. Un second `--order` est **interdit** (D-049).
- Pas d’URL Replit en dur dans ce rapport.

## Git

Compare : https://github.com/vgactech/artcb/compare/main...cursor/ovh4-baremetal-go-3c95  
Outil ManagePullRequest **absent** de cette session (`gh` lecture seule).
