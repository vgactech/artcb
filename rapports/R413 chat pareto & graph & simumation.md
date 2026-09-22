J’ai traité cette demande comme **un audit indépendant**, sans reprendre le verdict du premier audit comme hypothèse.

J’ai d’abord resynchronisé l’analyse avec le dépôt GitHub actuel. Le `main` vérifié pointe sur **`8c3ff3656521968de4684e371b4931734c814635`**, commit `R407 — Audit forensique live 503 : faux positif Accept header N2, aucun nouveau wallet/user détecté`, daté du **21 septembre 2026**. [ARTCB — commit actuel vérifié](https://github.com/vgactech/artcb/commit/8c3ff3656521968de4684e371b4931734c814635?utm_source=chatgpt.com)

### Expertises activées

* architecture blockchain et systèmes distribués ;
* analyse statique des dépendances Python ;
* théorie des graphes dirigés ;
* consensus / finalité / réplication ;
* P2P, gossip, synchronisation et failover ;
* cryptographie et signatures hybrides ;
* wallets et identité ;
* contrôle d'accès / Genesis / multi-tenant ;
* PoL, HBP, WorkID et règlement économique ;
* API / chemins d'exécution ;
* persistance et stockage ;
* analyse des tests et preuves live ;
* analyse Pareto / centralité fonctionnelle ;
* analyse des points uniques de défaillance.

Un point méthodologique important : **le dépôt contient beaucoup de composants**, mais une grande partie est périphérique par rapport au chemin permettant réellement de transformer une requête en état blockchain persistant. Le Pareto doit donc être calculé sur la **fonctionnalité effectivement traversée**, pas sur le nombre de fichiers.

---

# RAPPORT A — GRAPHE DIRECTIONNEL ARTCB

# RAPPORT A — Audit du graphe directionnel ARTCB

**Référentiel audité :** `vgactech/artcb`
**Révision :** `8c3ff3656521968de4684e371b4931734c814635`
**Date de référence :** 21 septembre 2026
**Nature :** audit indépendant du graphe fonctionnel et réseau

## 1. Expertises mobilisées

* Architecture blockchain distribuée
* Théorie des graphes
* P2P / réplication / synchronisation
* Consensus distribué
* Cryptographie
* Authentification et autorisation
* Genesis / domaines
* Wallet / identité
* PoL / HBP / règlement
* Persistance
* API et chemins d'exécution
* Tests E2E et validation live

---

# 2. Réponse définitive

Le graphe directionnel ARTCB est **partiellement implémenté et partiellement démontré**.

Il existe réellement dans le code plusieurs graphes superposés :

1. **graphe d'appel logiciel** ;
2. **graphe API → services** ;
3. **graphe blockchain → persistance** ;
4. **graphe P2P → nœuds** ;
5. **graphe identité → wallet → machine → travail** ;
6. **graphe Genesis / domaine / autorisation** ;
7. **graphe économique PoL → HBP → règlement**.

En revanche, il serait incorrect de dire que **le graphe distribué complet A → B → C → … → Z est déjà une topologie de consensus universelle**.

La distinction fondamentale est :

```text
GRAPHE LOGIQUE
    ≠
GRAPHE DES APPELS
    ≠
GRAPHE P2P
    ≠
GRAPHE DE CONSENSUS
    ≠
CONNEXIONS RÉSEAU PHYSIQUES
```

C'est l'un des résultats majeurs de cet audit.

---

# 3. Architecture fonctionnelle réellement observable

Le chemin principal peut actuellement être représenté ainsi :

```text
                 UTILISATEUR / AGENT
                         │
                         ▼
                       API
                         │
                         ▼
                Authentification
                         │
                         ▼
                 Authz / identité
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
          Wallet                 Domaine
             │                 ORG/GROUP
             │                       │
             └───────────┬───────────┘
                         ▼
                    Work / Job
                         │
                         ▼
                 MiningPipeline
                         │
                         ▼
                  ProtocolEngine
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
            HumanID   MachineID   WorkID
              │          │          │
              └──────────┼──────────┘
                         ▼
                    capacité
                         │
                         ▼
                   partitionnement
                         │
                         ▼
                        PoL
                         │
                         ▼
                   HBP / OwnerDecay
                         │
                         ▼
                     Settlement
                         │
                         ▼
                   EconomicRoot
                         │
                         ▼
                     BlockHash
                         │
                         ▼
                  ChainManager
                         │
                         ▼
                  Public Ledger
                         │
                         ▼
                    P2P Sync
                    /       \
                   ▼         ▼
                 Node B     Node C
                   │         │
                   └────┬────┘
                        ▼
                  état répliqué
```

Cette chaîne n'est pas théorique : plusieurs de ses composants existent effectivement dans le `main`.

---

# 4. Noyau blockchain

Le composant central est :

`src/artcb/chain/manager.py`

Il fait actuellement beaucoup plus que simplement « écrire un bloc ».

Il concentre notamment :

* représentation des blocs ;
* lecture/écriture ;
* ledger public/privé ;
* calcul du tip ;
* validation de chaîne ;
* vérification cryptographique ;
* import de blocs ;
* append ;
* récompense ;
* settlement ;
* WorkID ;
* Anti-Sybil ;
* slashing ;
* economic root ;
* signatures hybrides ;
* intégration des registres d'identité.

Le fichier fait environ **1 500 lignes**.

Mais le point important n'est pas sa taille.

C'est sa **position dans le graphe**.

Une grande partie du système converge vers `ChainManager`.

[`src/artcb/chain/manager.py` — code audité](https://github.com/vgactech/artcb/blob/main/src/artcb/chain/manager.py?utm_source=chatgpt.com)

---

# 5. Consensus : attention à une confusion importante

Le code contient bien :

`src/artcb/consensus/live_bft.py`

et un protocole :

```text
N >= 3F + 1
Q = 2F + 1
```

Pour quatre nœuds :

```text
N = 4
F = 1
Q = 3
```

Mais ce mécanisme n'est **pas actuellement le consensus PBFT général de chaque append de bloc public**.

Le propre code de `tip_attest.py` le précise explicitement :

```text
not_pbft_view_change = True
not_block_append_bft = True
```

Et `live_bft.py` indique que son domaine principal est le **settlement / WorkID**, tandis que la finalité publique utilise une couche distincte.

Donc :

```text
Live BFT
   │
   └── settlement / prepare / commit

Tip Attestation
   │
   └── observation d'un tip commun

Public finality
   │
   └── mécanisme distinct

Block append
   │
   └── ne doit pas être décrit comme "PBFT général"
```

C'est une distinction critique.

[`src/artcb/consensus/live_bft.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/consensus/live_bft.py?utm_source=chatgpt.com)
[`src/artcb/consensus/tip_attest.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/consensus/tip_attest.py?utm_source=chatgpt.com)

---

# 6. Graphe P2P

Le graphe P2P réel contient notamment :

```text
PeerManager
     │
     ▼
P2PSyncService
     │
 ┌───┴────┐
 ▼        ▼
PULL     PUSH
 │        │
 ▼        ▼
Node A ↔ Node B
```

`sync.py` contient :

* synchronisation publique ;
* import ;
* push ;
* pull ;
* vérification structurelle ;
* chiffrement des enveloppes ;
* décision d'import ;
* protection contre l'equivocation ;
* synchronisation de plusieurs pairs.

Le service expose aussi :

```text
sync_all_peers()
```

qui effectue pull + push pour les pairs connus.

[`src/artcb/p2p/sync.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/p2p/sync.py?utm_source=chatgpt.com)

---

# 7. Mais le graphe P2P n'est pas nécessairement le graphe logique A → Z

Le registre `gossip.py` existe.

Cependant son rôle est principalement :

```text
annonces
pairs
symboles
découverte
```

Il ne faut donc pas l'interpréter comme :

```text
Gossip = consensus
```

ou :

```text
Gossip = finalité
```

Ce sont trois fonctions différentes.

[`src/artcb/p2p/gossip.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/p2p/gossip.py?utm_source=chatgpt.com)

---

# 8. A → Z

La propagation logique peut être décrite ainsi :

```text
A
│
├── API
│
├── authentification
│
├── identité
│
├── validation
│
├── transaction / travail
│
├── PoL
│
├── règlement
│
├── bloc
│
├── persistance
│
└── P2P
       │
       ▼
       B
       │
       ▼
       C
       │
       ▼
       D
```

Mais il manque une preuve permettant d'affirmer :

> « Tout événement A est obligatoirement propagé à chaque nœud par un chemin déterministe A → B → C → D. »

Le code permet différentes formes de synchronisation.

Ce n'est donc pas un simple anneau :

```text
A → B → C → D → A
```

ni nécessairement une chaîne :

```text
A → B → C → D
```

C'est plutôt un **graphe dynamique de pairs**, avec des mécanismes pull/push et des contrôles d'import.

---

# 9. A → Z et Z → A

## A → Z

La direction fonctionnelle est largement présente :

```text
client
 ↓
API
 ↓
state
 ↓
pipeline
 ↓
chain
 ↓
ledger
 ↓
P2P
 ↓
peer
```

## Z → A

Le retour est beaucoup moins linéaire.

Il s'effectue plutôt par :

```text
peer
 ↓
P2P response
 ↓
API/state
 ↓
lecture du ledger
 ↓
API response
 ↓
client
```

Il ne s'agit donc pas d'un graphe bidirectionnel unique.

C'est **deux familles de flux** :

```text
DATA / COMMAND FLOW
        A → réseau

RESPONSE / STATE FLOW
        réseau → A
```

---

# 10. Genesis

`src/artcb/authz/domains.py` formalise quatre niveaux conceptuels :

```text
GLOBAL
ORG
GROUP
USER / RESOURCE
```

Le point important est que le Genesis ORG/GROUP n'est pas assimilable au contenu privé.

Le code distingue notamment :

```text
Genesis
commitment
authorized_nodes
private Genesis body
legal owner
controller
```

Le réseau peut donc connaître un engagement public sans nécessairement posséder les données privées correspondantes.

[`src/artcb/authz/domains.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/authz/domains.py?utm_source=chatgpt.com)

---

# 11. Graphe des permissions

Le modèle est également directionnel :

```text
Founder
   │
   ▼
Authority
   │
   ▼
Policy
   │
 ┌─┴─────────┐
 ▼           ▼
GRANT      DELEGATE
 │           │
 └────┬──────┘
      ▼
   Principal
      │
      ▼
   Resource
```

Cela ne signifie cependant pas que toutes les relations organisationnelles imaginées dans la spécification complète sont déjà devenues un consensus global distribué.

C'est encore une zone où il faut séparer :

```text
modèle d'autorisation
        ≠
réplication
        ≠
consensus
```

---

# 12. Verdict du Rapport A

| Élément                                        | État                                       |
| ---------------------------------------------- | ------------------------------------------ |
| Graphe logiciel directionnel                   | **Implémenté**                             |
| API → services                                 | **Implémenté**                             |
| Identité → machine → travail                   | **Implémenté**                             |
| PoL → settlement                               | **Implémenté**                             |
| Chain → persistence                            | **Implémenté**                             |
| P2P pull/push                                  | **Implémenté**                             |
| Graphe de pairs                                | **Implémenté**                             |
| Attestation de tip                             | **Implémentée**                            |
| BFT settlement                                 | **Implémenté**                             |
| Consensus BFT général de tout append public    | **Non démontré comme tel**                 |
| Graphe A→Z complet garanti                     | **Partiel**                                |
| Graphe Z→A complet garanti                     | **Partiel**                                |
| Topologie physique identique au graphe logique | **Faux**                                   |
| Propagation complète de tout état privé        | **Non**                                    |
| Réplication publique complète                  | **Partiellement démontrée selon scénario** |
| Résilience totale après panne arbitraire       | **Non démontrée**                          |

## Conclusion

Le graphe ARTCB **existe réellement**, mais il faut le décrire comme un **ensemble de graphes superposés**, et non comme un unique graphe universel.

La structure actuelle est suffisamment réelle pour permettre une analyse de centralité.

C'est précisément cette centralité qui constitue le sujet du Rapport B.

---

# RAPPORT B — PARETO 20/80

# RAPPORT B — Audit Pareto 20/80 ARTCB

**Référentiel :** `vgactech/artcb`
**Commit audité :** `8c3ff3656521968de4684e371b4931734c814635`
**Date :** 21 septembre 2026
**Objet :** identifier les composants portant la majorité de la fonctionnalité critique.

---

# 1. Méthode

Le Pareto n'est pas calculé à partir du nombre de lignes.

Pour chaque composant, j'utilise conceptuellement :

$$
C_i =
D_{in}
+D_{out}
+U
+CP
+CS
+CD
+CN
+CT
+CI
+F
$$

où :

* \(D_{in}\) = dépendances entrantes ;
* \(D_{out}\) = dépendances sortantes ;
* \(U\) = utilisation ;
* \(CP\) = présence dans les chemins critiques ;
* \(CS\) = influence consensus ;
* \(CD\) = influence données ;
* \(CN\) = influence réseau ;
* \(CT\) = influence transactions ;
* \(CI\) = influence identité/permissions ;
* \(F\) = impact d'une panne.

J'ajoute ensuite une distinction essentielle :

```text
CENTRALITÉ TECHNIQUE
        ≠
CRITICITÉ OPÉRATIONNELLE
```

Un module peut être très utilisé mais remplaçable.

Inversement, un module de 100 lignes peut être un verrou de sécurité.

---

# 2. Résultat principal

Le système ARTCB ne présente pas une distribution uniforme de sa criticité.

La fonctionnalité critique se concentre fortement autour de quelques familles :

```text
                 ARTCB
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
      API       PROTOCOL     CHAIN
        │          │          │
        │          │          ├── Persistence
        │          │          ├── Hash
        │          │          └── Settlement
        │          │
        │          ├── Identity
        │          ├── WorkID
        │          ├── PoL
        │          └── Economics
        │
        └── AuthZ / Wallet
                   │
                   ▼
                  P2P
                   │
             Replication
```

---

# 3. Noyau absolument critique — catégorie A

## A1 — `ChainManager`

**Criticité : extrêmement élevée**

Pourquoi ?

Parce qu'il concentre :

* représentation du bloc ;
* persistance ;
* hash ;
* signature ;
* validation ;
* append ;
* import ;
* tip ;
* public/private ledger ;
* settlement ;
* récompense ;
* WorkID ;
* sécurité ;
* identité économique.

C'est probablement **le composant le plus central du système actuel**.

[`src/artcb/chain/manager.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/chain/manager.py?utm_source=chatgpt.com)

### Processus

```text
Transaction / travail
        ↓
ChainManager
        ↓
Bloc
        ↓
Ledger
```

### Problème

Une panne ou une modification incorrecte peut affecter simultanément plusieurs couches.

### Conséquence

Il s'agit d'un **hotspot architectural**.

Le danger n'est pas uniquement le bug.

C'est aussi le risque de modification :

```text
chain change
   ↓
economics regression
   ↓
settlement regression
   ↓
replication regression
```

---

# 4. A2 — `ProtocolEngine`

`src/artcb/mining/protocol.py`

Le module annonce explicitement son rôle :

```text
HumanID
DeviceID
WalletID
MachineID
WorkID
PB
PoL
HBP
settlement
```

C'est donc un **orchestrateur transversal**.

[`src/artcb/mining/protocol.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/mining/protocol.py?utm_source=chatgpt.com)

### Pourquoi il est critique

Il relie :

```text
identité
 ↓
machine
 ↓
travail
 ↓
capacité
 ↓
partition
 ↓
PoL
 ↓
HBP
 ↓
settlement
 ↓
chain
```

Il possède donc une centralité fonctionnelle supérieure à celle que suggère son nombre de lignes.

---

# 5. A3 — `build_app_state()` / `AppState`

`src/api/deps.py`

Ce module est sous-estimé.

Il initialise ou relie notamment :

* ChainManager ;
* HumanRegistry ;
* MachineRegistry ;
* WorkRegistry ;
* ProtocolEngine ;
* GroupManager ;
* AuthzGate ;
* IR ;
* mémoire ;
* P2P ;
* wallets ;
* PoolService ;
* timeline ;
* sécurité.

Autrement dit :

```text
Application
     ↓
build_app_state()
     ↓
quasiment tout le système
```

[`src/api/deps.py`](https://github.com/vgactech/artcb/blob/main/src/api/deps.py?utm_source=chatgpt.com)

### C'est un exemple parfait de composant sous-estimé.

Il n'est pas nécessairement le composant métier le plus important.

Mais une mauvaise initialisation ici peut casser :

```text
API
+
chain
+
P2P
+
identity
+
economics
+
groups
```

---

# 6. A4 — `MiningPipeline`

`src/artcb/mining/pipeline.py`

Le chemin est :

```text
texte / job
   ↓
IR
   ↓
critic
   ↓
PoL
   ↓
contributors
   ↓
ChainManager
```

Le pipeline est donc le pont entre :

```text
travail IA
```

et

```text
bloc blockchain
```

[`src/artcb/mining/pipeline.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/mining/pipeline.py?utm_source=chatgpt.com)

---

# 7. A5 — `P2PSyncService`

`src/artcb/p2p/sync.py`

Ce module porte la continuité distribuée :

```text
Node A
  │
  ├── push
  │
  └── pull
       │
       ▼
Node B
```

Il contient aussi les décisions d'import.

Donc une erreur ici peut provoquer :

```text
fork
non-réplication
rejet incorrect
import dangereux
divergence
```

[`src/artcb/p2p/sync.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/p2p/sync.py?utm_source=chatgpt.com)

---

# 8. A6 — AuthZ / Genesis

La famille :

```text
src/artcb/authz/
```

est moins volumineuse que certaines autres parties du projet, mais extrêmement importante.

Elle contrôle :

```text
qui
   ↓
peut faire quoi
   ↓
sur quelle ressource
```

Elle relie :

```text
identity
   ↓
principal
   ↓
policy
   ↓
resource
```

et le modèle Genesis/domaine.

[`src/artcb/authz/gate.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/authz/gate.py?utm_source=chatgpt.com)
[`src/artcb/authz/engine.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/authz/engine.py?utm_source=chatgpt.com)
[`src/artcb/authz/genesis.py`](https://github.com/vgactech/artcb/blob/main/src/artcb/authz/genesis.py?utm_source=chatgpt.com)

---

# 9. A7 — Identity / Machine / WorkID

La chaîne économique est :

```text
HumanID
   ↓
MachineID
   ↓
WalletID
   ↓
WorkID
   ↓
Settlement
```

C'est extrêmement important pour ARTCB car l'économie ne dépend pas seulement d'une signature cryptographique.

Elle dépend de la relation entre :

```text
humain
machine
travail
wallet
règlement
```

Une erreur d'identité peut donc devenir une erreur économique.

---

# 10. A8 — `ChainManager.import_extending_block()`

Voici un cas particulièrement important.

Ce n'est pas seulement :

```text
ChainManager
```

qui est critique.

Une fonction relativement localisée comme :

```text
import_extending_block()
```

peut être plus critique que de nombreux modules entiers.

Elle intervient dans :

```text
P2P
 ↓
réception bloc
 ↓
validation
 ↓
Byzantine guard
 ↓
signature
 ↓
extension
 ↓
persistance
```

### C'est exactement le type de fonction que ton Pareto devait rechercher.

---

# 11. B — Composants fortement dépendants

Les composants de catégorie B comprennent notamment :

| Composant                 | Fonction              |
| ------------------------- | --------------------- |
| `api/routes.py`           | façade API principale |
| `api/p2p_routes.py`       | entrée P2P HTTP       |
| `api/groups_routes.py`    | groupes               |
| `api/auth_routes.py`      | sessions              |
| `wallet/manager.py`       | wallets               |
| `wallet/encryption.py`    | protection des clés   |
| `p2p/peers.py`            | registre des pairs    |
| `p2p/node_identity.py`    | identité du nœud      |
| `consensus/live_bft.py`   | règlement BFT         |
| `consensus/tip_attest.py` | attestation du tip    |
| `economics/settlement.py` | règlement économique  |
| `economics/workid.py`     | unicité du travail    |
| `security/anti_sybil.py`  | anti-Sybil            |
| `crypto/hybrid.py`        | signature hybride     |
| `crypto/pqc.py`           | PQC                   |
| `groups/manager.py`       | groupes               |
| `ir/encoder.py`           | représentation IR     |
| `pol/scorer.py`           | score PoL             |

---

# 12. C — Composants périphériques

Ils peuvent être importants sans être nécessaires au noyau blockchain.

Exemples :

```text
notifications
dashboard
frontend
PDF loader
connecteurs externes
Gradium
certaines intégrations
visualisation
analytics
certaines fonctions MCP
```

Une panne de ces composants peut dégrader l'expérience utilisateur sans nécessairement empêcher :

```text
validation
bloc
persistance
réplication
```

---

# 13. D — Redondance

Plusieurs fonctions peuvent produire des effets proches.

Exemple :

```text
API mining
      │
      ├── MiningPipeline
      │
      └── ProtocolEngine
```

Autre exemple :

```text
tip_attestation
       +
public tip watchdog
       +
PBFT finality
```

Ces composants ne sont pas équivalents, mais ils interviennent tous autour de la notion de :

```text
état courant
+
convergence
+
finalité
```

Cela crée une **redondance fonctionnelle partielle**, mais pas une redondance permettant simplement de supprimer l'un d'eux.

---

# 14. Composants sous-estimés

C'est l'une des conclusions les plus importantes de l'audit.

## Sous-estimé n°1 — `build_app_state()`

Très petit relativement à l'ensemble du système.

Mais :

```text
build_app_state
      ↓
Chain
Protocol
Identity
P2P
Groups
AuthZ
Memory
Pool
```

Donc :

> faible taille ≠ faible criticité.

---

## Sous-estimé n°2 — `decide_public_import()`

Dans `p2p/sync.py`.

Une fonction de décision relativement petite peut déterminer :

```text
ACCEPTER
ou
REFUSER
```

un bloc entrant.

Son impact est donc beaucoup plus grand que sa taille.

---

## Sous-estimé n°3 — `verify_attest()`

Une fonction courte.

Mais elle touche :

```text
signature
node identity
tip
consensus observation
```

Une erreur peut fausser la perception de convergence.

---

## Sous-estimé n°4 — `workid` uniqueness

Une fonction ou une petite couche empêchant :

```text
même travail
   ↓
double règlement
```

peut avoir une importance économique énorme.

---

## Sous-estimé n°5 — `AuthzGate`

Quelques fonctions d'autorisation peuvent décider :

```text
ALLOW
DENY
```

pour une énorme quantité de ressources.

---

# 15. Le vrai chemin critique minimal

Après réduction de toutes les fonctionnalités périphériques, le chemin minimal ressemble à :

```text
Utilisateur / Agent
       ↓
API
       ↓
Authentification
       ↓
Identité / AuthZ
       ↓
Transaction / Work
       ↓
Validation
       ↓
PoL / règles protocolaires
       ↓
ChainManager
       ↓
Hash / signature
       ↓
Public Ledger
       ↓
P2P
       ↓
Import validation
       ↓
Persistance
```

Pour les opérations économiques :

```text
Human
 ↓
Machine
 ↓
Wallet
 ↓
WorkID
 ↓
PoL
 ↓
HBP / OwnerDecay
 ↓
Settlement
 ↓
EconomicRoot
 ↓
Block
```

---

# 16. Les composants qu'on peut casser sans arrêter complètement ARTCB

On peut raisonnablement considérer comme périphériques au noyau :

```text
Dashboard
Frontend
Notifications
Certaines intégrations LLM
Gradium
PDF ingestion
Certaines fonctions MCP
Visualisation
Analytics
```

La blockchain peut continuer à fonctionner si ces composants sont absents, à condition que le chemin API/protocole minimal reste disponible.

---

# 17. Les composants qu'il serait dangereux de modifier

Catégorie de risque maximale :

### Niveau R0

```text
ChainManager
ProtocolEngine
P2PSyncService
AuthZ
WorkID
Settlement
Public finality
```

### Niveau R1

```text
Wallet
Identity
Anti-Sybil
Crypto
PoL
MachineRegistry
HumanRegistry
```

### Niveau R2

```text
API
Groups
Pool
IR
Memory
```

### Niveau R3

```text
Dashboard
Notifications
Connecteurs
Frontend
```

Ce ne sont pas des « scores de qualité ». Ce sont des **zones de blast radius**.

---

# 18. Estimation Pareto

Il faut être précis sur ce point.

Je ne peux pas honnêtement annoncer :

> « exactement 20,00 % des fichiers produisent exactement 80,00 % de la fonctionnalité »

car cela nécessiterait une extraction exhaustive du graphe d'appels Python, y compris les appels dynamiques, les imports conditionnels, les dépendances runtime et les chemins API réellement exécutés.

En revanche, l'analyse actuelle permet une estimation structurelle robuste.

### Noyau fonctionnel approximatif

Sur l'ensemble des composants logiciels d'ARTCB, le noyau critique apparaît concentré autour de **deux ordres de grandeur** :

```text
≈ 15–25 % des composants
        ↓
≈ 70–85 % de la fonctionnalité blockchain critique
```

Le centre de gravité se trouve essentiellement dans :

```text
Chain
Protocol
API state
P2P sync
AuthZ
Identity
WorkID
Settlement
Consensus/finality
Wallet/crypto
PoL
```

Donc l'hypothèse :

$$
20\% \rightarrow \sim80\%
$$

est **structurellement plausible**, mais **pas encore mesurée au centième près**.

---

# 19. Pareto par famille

Une représentation plus utile est :

| Famille                        | Part approximative de la criticité |
| ------------------------------ | ---------------------------------: |
| Chain / ledger / validation    |                        Très élevée |
| Protocol / mining              |                        Très élevée |
| P2P / synchronisation          |                        Très élevée |
| Identity / WorkID / settlement |                             Élevée |
| AuthZ / Genesis                |                             Élevée |
| Consensus / finality           |                             Élevée |
| Wallet / crypto                |                             Élevée |
| PoL                            |                   Moyenne à élevée |
| Groups                         |                            Moyenne |
| IR / mémoire                   |                            Moyenne |
| Pool                           |                            Moyenne |
| API périphériques              |                   Faible à moyenne |
| UI / dashboard                 |                             Faible |
| intégrations externes          |                             Faible |

---

# 20. Le vrai Pareto n'est donc pas « 20 % des fichiers »

La bonne définition est :

```text
20 %
des chemins fonctionnels critiques
             ↓
≈ 80 %
des conséquences système
```

C'est beaucoup plus pertinent.

Par exemple :

```text
decide_public_import()
```

peut avoir davantage d'importance systémique que :

```text
1000 lignes de dashboard
```

---

# 21. Point unique de défaillance principal

Le plus gros risque architectural actuellement identifié est la **concentration de responsabilités dans ChainManager**.

```text
                    ChainManager
                 /       |       \
                /        |        \
          persistence  crypto   economics
              │          │          │
              ▼          ▼          ▼
             P2P       block      settlement
```

Cela donne une forte centralité.

Mais cela crée également un **blast radius important**.

Une modification de :

```text
append_block()
```

peut toucher simultanément :

```text
reward
hash
settlement
workid
identity
ledger
replication
```

C'est précisément le type de composant qui doit avoir des tests de régression extrêmement larges.

---

# 22. Deuxième concentration : `ProtocolEngine`

Même problème à un niveau différent :

```text
Human
Machine
Wallet
Work
Capacity
Partition
PoL
HBP
Settlement
```

Tout converge vers le protocole.

Cela en fait le **centre économique** d'ARTCB.

---

# 23. Troisième concentration : `AppState`

Il constitue le **centre d'assemblage**.

```text
AppState
 ├── Chain
 ├── Protocol
 ├── P2P
 ├── Identity
 ├── Groups
 ├── AuthZ
 ├── Memory
 ├── Pool
 └── API
```

Il s'agit moins d'un centre de calcul que d'un **centre de dépendances**.

---

# 24. Quatrième concentration : P2P Sync

Sans P2P :

```text
Node A
```

peut continuer localement.

Mais :

```text
ARTCB distribué
```

perd sa propriété essentielle de réplication.

Donc :

```text
P2P
```

est périphérique pour une blockchain locale,

mais

```text
P2P
```

est absolument critique pour une blockchain distribuée.

---

# 25. Spécification → Code → Tests → Mesures → Conclusion

## Chain

**Spécification :** chaîne blockchain persistante.

**Code :** oui.

**Tests :** oui, nombreuses suites `test_chain`, E2E et tests de validation.

**Mesure réelle :** oui pour plusieurs opérations, mais cela ne prouve pas automatiquement toutes les propriétés distribuées.

**Conclusion :** noyau réellement implémenté.

---

## P2P

**Spécification :** réplication entre nœuds.

**Code :** oui.

**Tests :** oui.

**Mesures live :** oui pour plusieurs scénarios de connectivité et propagation.

**Conclusion :** mécanisme réel, mais la couverture de tous les scénarios de convergence/failover doit rester séparée de la simple connectivité.

---

## Consensus

**Spécification :** convergence/finalité distribuée.

**Code :** plusieurs mécanismes existent.

**Tests :** oui.

**Mesures :** certaines.

**Conclusion :** il faut éviter d'appeler tout le système « PBFT » : `live_bft.py` couvre explicitement le settlement et le code d'attestation indique lui-même qu'il ne constitue pas un PBFT général d'append public.

---

## Genesis / AuthZ

**Spécification :** domaines et contrôle d'accès.

**Code :** oui, avec séparation Global/ORG/GROUP/User/Resource.

**Tests :** oui.

**Mesures live :** beaucoup moins complètes que les tests locaux.

**Conclusion :** architecture réelle, mais toutes les propriétés distribuées de possession/migration/réplication ne sont pas encore démontrées au même niveau que le code local.

---

## PoL / HBP

**Spécification :** travail + identité + règlement.

**Code :** oui.

**Tests :** oui.

**Simulations :** nombreuses.

**Mesures live :** certaines parties existent.

**Conclusion :** mécanisme substantiellement implémenté, mais les simulations économiques ne doivent pas être confondues avec une preuve de comportement économique réel du réseau.

---

# 26. Les 20 % à concentrer pour l'audit

Si l'objectif est de maximiser l'efficacité de l'effort d'audit, le premier périmètre doit être :

```text
1. ChainManager
2. ProtocolEngine
3. AppState / build_app_state
4. P2PSyncService
5. public finality / PBFT
6. AuthZGate / AuthorizationEngine
7. HumanRegistry
8. MachineRegistry
9. WorkRegistry / WorkID
10. Settlement
11. WalletManager
12. crypto/signatures
13. PoL scorer
14. Anti-Sybil
15. fonctions d'import / validation
```

Puis, à l'intérieur de ces modules, auditer prioritairement les fonctions qui :

```text
ACCEPT / REJECT
CALCULATE
AUTHORIZE
IMPORT
APPEND
SETTLE
SIGN
VERIFY
REPLICATE
```

---

# 27. Les fonctions à traiter comme « fonctions rouges »

Ce sont les fonctions qui méritent une protection maximale contre les régressions :

```text
ChainManager.append_block()
ChainManager.import_extending_block()
ChainManager.verify_chain_integrity()
ChainManager.verify_block_dict()

ProtocolEngine.execute_block()

P2PSyncService.decide_public_import()
P2PSyncService.import_public_blocks()
P2PSyncService.pull_from_peer()
P2PSyncService.push_to_peer()

tip_attest.verify_attest()
tip_attest.quorum_from_attests()

WorkID settlement / uniqueness

settle_block()

AuthZGate authorization path

HumanRegistry verification
MachineRegistry binding

Wallet signing / key loading

PoL validation
```

---

# 28. Conclusion Pareto

Le résultat central de l'audit est :

```text
ARTCB
│
├── beaucoup de fonctionnalités
│
└── mais une concentration très forte
    autour de quelques chemins
```

Le véritable noyau est :

```text
                ┌─────────────┐
                │  AppState   │
                └──────┬──────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
      API          Protocol         AuthZ
        │              │              │
        │         ┌────┼────┐         │
        │         ▼    ▼    ▼         │
        │      Human Machine Work      │
        │         │    │    │          │
        │         └────┼────┘          │
        │              ▼               │
        │             PoL              │
        │              ▼               │
        └──────────► Chain ◄───────────┘
                       │
                  Settlement
                       │
                  Persistence
                       │
                      P2P
                       │
              ┌────────┼────────┐
              ▼        ▼        ▼
             N1       N2       N3/N4
```

### Verdict

**Oui : ARTCB possède un noyau Pareto très concentré.**

La zone qui porte la majorité de la fonctionnalité critique n'est pas le frontend, ni les centaines de fonctions périphériques.

Elle se concentre autour de :

> **Chain + Protocol + AppState + P2P Sync + Identity/WorkID + Settlement + AuthZ + Consensus/Finality + Wallet/Crypto + PoL.**

L'estimation structurée actuelle est :

$$
\boxed{\text{≈15–25 % des composants} \rightarrow \text{≈70–85 % de la criticité fonctionnelle}}
$$

avec **20 % → 80 % comme approximation de travail**, et non comme mesure scientifique finale.

La prochaine étape permettant de transformer cette estimation en véritable Pareto quantitatif serait un **graphe exhaustif AST des appels et imports du `main`**, avec :

```text
fonction → fonction
fonction → module
module → module
API → fonction
test → fonction
chemin critique → fonction
fonction → impact
```

puis calcul de :

```text
in-degree
out-degree
betweenness centrality
PageRank
fan-in
fan-out
critical-path frequency
failure blast radius
test coverage
live evidence coverage
```

À ce moment-là, on pourra produire un tableau du type :

```text
Rang | Fonction | Centralité | Chemins critiques | Impact panne | Tests | Live | Pareto cumulé
```

et déterminer mathématiquement quelles fonctions représentent réellement les **20 % critiques** plutôt que simplement les estimer.

## Synthèse opérationnelle

Le résultat des deux rapports peut donc être résumé sans ambiguïté :

```text
RAPPORT A
─────────
Le graphe existe.
Mais il est composé de plusieurs graphes superposés.
Le graphe P2P n'est pas le graphe de consensus.
Le graphe logique n'est pas la topologie physique.
Le BFT actuel n'est pas à présenter comme un PBFT universel
de chaque append public.
```

et :

```text
RAPPORT B
─────────
Le système est fortement concentré.
Le cœur critique est approximativement :

Chain
Protocol
AppState
P2P Sync
Identity
WorkID
Settlement
AuthZ
Consensus/Finality
Wallet/Crypto
PoL

≈ 15–25 % des composants
→ ≈ 70–85 % de la criticité fonctionnelle.
```

Le point le plus important découvert par le Pareto est probablement celui-ci : **les petites fonctions de décision (`import`, `authorize`, `verify`, `settle`, `append`) doivent être considérées comme plus critiques que de gros modules périphériques**. C'est là que l'audit de sécurité et les tests de régression doivent être concentrés en premier.
