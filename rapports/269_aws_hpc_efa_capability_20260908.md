# 269 — AWS HPC / EFA / ParallelCluster : ce qui est possible (mesure réelle)

Date : **2026-09-08T17:12:00Z**  
Compte : `599128160879` IAM `node_artcb_3_agent` région **eu-west-3**  
Source credentials : Doppler **`artcb3/dev`** (les secrets Cursor `AWS_API_KEY_AGENT_3` sont **invalides** / `InvalidClientTokenId`).  
**Aucun cluster lancé. Aucune hausse de quota demandée. Aucun secret imprimé.**

Live ARTCB (OVH1) au bootstrap de ce tour : SHA `db1bebc7…`, hauteur **1099**, tip `9c67ac06…`.

## Verdict en une phrase

Je **peux** appeler les API HPC (IAM `AdministratorAccess`, dry-run EFA = autorisé). Je **ne peux pas** activer un supercalculateur virtuel **maintenant** : quota HPC = **0 vCPU**, plus petite instance EFA = **24 vCPU**, nœud actuel = **t3.small sans EFA**, AWS Parallel Computing Service **non abonné**.

## Ce qui est vrai côté « géants du cloud »

AWS vend bien du HPC-as-a-Service : EFA (réseau OS-bypass / libfabric, **pas** InfiniBand), families `hpc7a` / `c6i.32xlarge`, ParallelCluster / PCS, placement groups `cluster`.  
Dans **ce** compte, à Paris, ce catalogue est **partiellement présent** et **intégralement bloqué par les quotas**.

## Mesures

| Question | Résultat mesuré |
|---|---|
| STS | OK, compte `599128160879` |
| IAM | `AdministratorAccess` + `AmazonEC2FullAccess` + `IAMFullAccess` |
| Instance live aws-node-3 | `i-085b74abd1aaf04ee` **t3.small** eu-west-3a, ENA oui, EFA **non** |
| SKU EFA dans eu-west-3 | **127** types |
| Plus petite SKU EFA | **hpc7a.12xlarge = 24 vCPU** (aucune ≤ 16 vCPU) |
| `hpc7a.*` offert | 12/24/48/96xlarge, **seulement eu-west-3a** pour 12xlarge |
| `hpc6id.32xlarge` | offert |
| `hpc6a` / `hpc7g` / `hpc8a` | **absent** à Paris |
| GPU `p4d` / `p5` | **absent** à Paris |
| GPU `g6.*` | offert, mais **pas en 3a** (3b/3c) |
| Quota Standard On-Demand | **16 vCPU** (t3.small en consomme 2) |
| Quota HPC On-Demand `L-F7808C92` | **0** |
| Quota G/VT, P, Inf, Trn | **0** |
| Dry-run `RunInstances` EFA `hpc7a.12xlarge` | **DryRunOperation** = IAM OK (le dry-run **ne teste pas** le quota) |
| Dry-run ENI `InterfaceType=efa` | IAM OK |
| Dry-run placement group `cluster` | IAM OK |
| SG actuel | 22/80/443/8000/8443 ; **pas** de règle « all traffic → self » exigée par EFA |
| AWS PCS `list-clusters` | **SubscriptionRequiredException** |
| CLI `pcluster` | **non installé** sur cet agent |
| InfiniBand | **non** — AWS = EFA/SRD |
| Prix catalogue Paris | `hpc7a.12xlarge` **8,5553 USD/h** ; `c6i.32xlarge` **6,464 USD/h** |

## Possible / pas possible

### Possible sans changer le compte (aujourd’hui)

- Continuer aws-node-3 en **t3.small** (déjà le cas).
- Lancer d’autres instances **standard** dans la limite des **~14 vCPU** restants (`c6i.xlarge` = 4 vCPU, etc.) — **sans EFA**.
- Créer un placement group `cluster` (IAM OK) — inutile sans nœuds HPC.
- Installer la CLI ParallelCluster plus tard (outil, pas une permission).

### Possible seulement après actions AWS (quota + argent)

1. Demander une hausse **Running On-Demand HPC instances** (`L-F7808C92`) ≥ 24 (mieux : 48–192 pour 2+ nœuds).
2. Pour EFA « compute dense » non-HPC : hausse **Standard** `L-1216C47A` ≥ 128 pour un `c6i.32xlarge`.
3. Ajouter sur le SG la règle **all protocols, source = ce SG**.
4. Lancer des instances **nouvelles** (on ne « active » pas EFA sur le t3.small existant).
5. ParallelCluster : créer le cluster CloudFormation **après** quotas. PCS : d’abord **s’abonner** au service.

Un nœud `hpc7a.12xlarge` ≈ **8,56 USD/h**. Huit nœuds ≈ **68 USD/h**. Ce n’est pas un clic gratuit.

### Impossible dans eu-west-3 (catalogue régional)

- InfiniBand physique.
- Supercalculateur GPU type **P5 / P4d** à Paris (SKU absents).
- `hpc6a` / `hpc7g` / `hpc8a` à Paris.
- « Activer EFA » sur `i-085b74abd1aaf04ee` sans la remplacer.
- Prétendre qu’ARTCB tourne déjà sur un fabric HPC : le nœud 3 est un **t3.small**.

### Non fait volontairement

- Aucun `RunInstances` réel HPC/GPU.
- Aucune `RequestServiceQuotaIncrease`.
- Pas de stack ParallelCluster.
- Pas de toucher OVH1.

## Clés Cursor vs Doppler

`AWS_API_KEY_AGENT_3` (Cursor) → STS **InvalidClientTokenId**.  
`AWS_ACCESS_KEY_ID` dans **artcb3/dev** → STS OK.  
Les alias Cursor sont **périmés** ; l’accès réel de cet agent passe par Doppler nœud 3.

## Conclusion

**HPC-as-a-Service AWS : le compte a les droits IAM pour le provisionner, pas les quotas ni le réseau EFA déjà câblés, et Paris n’a pas les GPU P5.**  
Activer un vrai cluster EFA/ParallelCluster est un **ordre explicite** (hausse de quota + budget horaire), pas un interrupteur déjà allumé.
