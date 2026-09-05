Oui. Et je dois corriger un point important de ma réponse précédente :

> **« un nœud = un domaine » était une simplification trop forte.**

Dans l’architecture actuelle d’ARTCB, **un utilisateur n’a pas besoin d’avoir installé un nœud pour créer une organisation ou un groupe**. En revanche, **le serveur ARTCB auquel il se connecte devient actuellement le lieu où le Genesis privé de cette organisation/groupe est créé et conservé**.

C’est précisément là qu’il faut distinguer **identité**, **propriété**, **stockage** et **réplication**.

J’ai recroisé le code actuel de `main` avec les éléments de tes audits.

---

# 1. Ton scénario est bien possible

Prenons exactement ton exemple.

Tu as actuellement :

```text
                    RÉSEAU ARTCB
                         │
        ┌────────────────┼────────────────┐
        │                │                │
     Nœud A           Nœud B           Nœud C           Nœud D
        │
      API
        │
     Interface Web
        │
      Alice
```

Alice :

* n'a jamais installé ARTCB ;
* n'a aucun serveur ;
* n'a pas de nœud ;
* ouvre simplement l'interface Web ;
* connecte/crée son wallet ;
* crée `Organisation Alice` ;
* puis éventuellement `Groupe Alice`.

**Elle peut parfaitement faire cela.**

Pourquoi ?

Parce que son navigateur n'a pas besoin d'exécuter la blockchain.

Il envoie une requête HTTP à un nœud ARTCB.

Le code actuel fait justement :

```text
Navigateur Alice
      │
      │ POST /api/v1/authz/orgs
      ▼
Serveur ARTCB
      │
      ▼
AuthzGate
      │
      ▼
GenesisStore
      │
      ▼
ORG GENESIS
```

La route `/api/v1/authz/orgs` authentifie le principal puis appelle `gate.genesis.create_org(...)`.

Donc **Alice n'a pas besoin d'un serveur personnel pour créer son organisation**.

---

# 2. Mais où est réellement créé son Genesis aujourd'hui ?

C'est ici que ta question devient extrêmement importante.

Le code actuel contient :

```text
GenesisStore(root / "orgs.json")
```

où `root` est :

```text
data_dir / "authz"
```

Donc le stockage est local au processus/nœud ARTCB qui reçoit la requête.

Concrètement, si Alice arrive sur :

```text
https://node-A.artcb...
```

et crée :

```text
Organisation Alice
```

le scénario actuel est conceptuellement :

```text
NODE A
└── data/
    └── authz/
        ├── orgs.json
        ├── group_genesis.json
        ├── commitments.jsonl
        └── ...
```

Le `ORG GENESIS BODY` est donc **local au domaine/nœud qui l'a créé**.

Le fichier `genesis.py` le dit explicitement :

> les corps des Genesis ORG/GROUP restent dans le local domain store ; seuls les engagements publics — type + ID + hash — sont destinés à être exposés au réseau.

---

# 3. Et pour un groupe ?

C'est exactement le même principe.

Quand Alice crée :

```text
Organisation A
       │
       └── Groupe X
```

la route actuelle fait :

```text
group = mgr.create_group(...)
```

puis :

```text
authz.genesis.create_group_genesis(...)
```

Le code crée donc le `GROUP GENESIS` **sur le serveur qui traite la requête**.

Et `GenesisStore` écrit ensuite le Genesis dans :

```text
group_genesis.json
```

puis crée également une entrée de commitment.

---

# 4. Attention : Genesis ≠ propriété du serveur

C'est probablement **le point le plus important pour résoudre ta confusion**.

Si Alice crée son organisation sur le nœud A :

```text
                    Alice
                      │
                      │ crée ORG
                      ▼
                   NŒUD A
                      │
                      ▼
              ORG GENESIS BODY
```

cela **ne devrait pas signifier** :

> « le nœud A est propriétaire de l'organisation ».

Ce serait une mauvaise architecture.

Il faut plutôt avoir :

```text
Alice
 │
 ├── founder_address = WALLET_ALICE
 │
 └── Organisation A
          │
          ├── organization_id
          ├── founder_address
          ├── governance_root
          ├── membership_root
          ├── policy_root
          └── content_hash
```

Le code actuel fait déjà une partie de cela : `OrgGenesis` contient notamment `organization_id`, `founder_address`, `governance_root`, `membership_root`, `policy_root`, etc.

Donc :

### Le serveur est actuellement le **lieu de stockage**.

Il ne devrait pas être la **racine de propriété**.

La propriété doit être cryptographiquement liée à l'identité du fondateur.

---

# 5. Et là, ton problème futur apparaît

Imaginons :

```text
Jour 1

Alice
  │
  ▼
Node A
  │
  └── Organisation Alice
```

Puis Node A disparaît.

Si tout le Genesis privé était uniquement là :

```text
Node A
└── orgs.json
      └── Organisation Alice
```

alors Alice pourrait perdre **l'accès opérationnel au body du Genesis**, même si son identité/fondateur existe encore ailleurs.

C'est précisément pourquoi je ne recommande **pas** que l'architecture finale reste :

```text
créateur → serveur choisi → stockage définitif
```

Il faut évoluer vers :

```text
créateur
   │
   ▼
identité cryptographique
   │
   ▼
ORG_ID
   │
   ├──────────► commitment global
   │
   └──────────► domain storage
                   │
                   ├── Node A
                   ├── Node B
                   └── Node X
```

---

# 6. Le code actuel prévoit déjà une séparation très intéressante

Le fichier `domains.py` définit explicitement quatre niveaux.

### Niveau 1 — GLOBAL GENESIS

```text
GLOBAL GENESIS
```

Répliqué :

```text
tous les nœuds de consensus
```

### Niveau 2 — ORG GENESIS

```text
ORG GENESIS BODY
```

Actuellement :

```text
org_domain_nodes
```

### Niveau 3 — GROUP GENESIS

```text
GROUP GENESIS BODY
```

Actuellement :

```text
group_domain_nodes
```

### Niveau 4 — USER / RESOURCE

```text
USER DOMAIN
PRIVATE RESOURCE
```

avec des niveaux de confidentialité encore plus élevés.

Le projet indique également :

```text
P2P_SYNCS_PRIVATE_BLOCKS = False
```

et précise que les blocs privés ne sont pas répliqués via le P2P public.

---

# 7. Donc tes quatre serveurs ne doivent PAS tous recevoir tout

C'est essentiel.

Tu ne veux pas :

```text
ORG Alice
     │
     ├── Node A
     ├── Node B
     ├── Node C
     └── Node D
```

avec le contenu privé complet sur les quatre, automatiquement.

Cela détruirait une partie de l'objectif de séparation des domaines.

Tu veux plutôt quelque chose comme :

```text
                   GLOBAL ARTCB
                        │
            ┌───────────┴───────────┐
            │                       │
      ORG_A commitment        GROUP_X commitment
       id + hash                id + hash
            │                       │
            ▼                       ▼
       Domaine ORG_A           Domaine GROUP_X
            │                       │
       ┌────┴────┐             ┌────┴────┐
       │         │             │         │
     Node A    Node B        Node B    Node C
```

Le réseau connaît :

```text
ORG_A existe
ORG_A = hash XYZ
```

mais ne reçoit pas nécessairement :

```text
liste des membres
documents
données privées
politiques privées complètes
```

C'est exactement la distinction prévue par la matrice actuelle.

---

# 8. Mais alors comment Alice récupère son organisation ?

C'est ici que je vois **le principal élément qui doit encore être renforcé**.

Aujourd'hui, le modèle est essentiellement :

```text
Alice
 │
 ▼
Node A
 │
 └── GenesisStore local
```

Il manque, à mon avis, une vraie notion de :

# **Domain Ownership + Domain Recovery**

Il faut que l'organisation soit récupérable indépendamment du serveur initial.

---

# 9. Je recommande un mécanisme de « Domain Manifest »

Par exemple :

```json
{
  "organization_id": "org_xxxxx",
  "founder_address": "wallet_alice",
  "genesis_hash": "abc123...",
  "domain_id": "domain_xxxxx",
  "domain_type": "organization",
  "created_at": "...",
  "storage_policy": {
    "replication": "selected_domain_nodes"
  }
}
```

Ce manifeste serait beaucoup plus important que :

```text
Node A possède orgs.json
```

Parce qu'il dit :

> « Voici l'identité de l'organisation et comment retrouver son domaine. »

---

# 10. Et là on arrive à ton idée : choisir le serveur

Oui, **c'est une excellente possibilité**, mais je ne ferais pas du simple choix :

> « Je choisis Node A. »

Je ferais plutôt :

### Choix du domaine de stockage

Lors de la création :

```text
Créer votre organisation

Nom :
[ ACME ]

Fondateur :
[ Wallet XYZ ]

Stockage du domaine :

○ Hébergé par ARTCB
○ Mes propres serveurs
○ Sélectionner des nœuds
○ Mode hybride
```

---

# 11. Quatre modes pourraient être proposés

## MODE A — Hébergement ARTCB

Pour l'utilisateur normal.

```text
Alice
 │
 ▼
Interface ARTCB
 │
 ▼
ARTCB attribue automatiquement
un ou plusieurs Domain Nodes
```

Alice n'a rien à installer.

C'est le mode le plus simple.

---

# 12. MODE B — Serveur choisi

Alice pourrait dire :

```text
ORG ACME

Domain Nodes :

☑ Node Paris
☑ Node Frankfurt
☐ Node Singapore
```

Le système enregistre :

```text
domain_id = D123

replicas:
    node_paris
    node_frankfurt
```

Le Genesis est alors répliqué **entre les nœuds de domaine autorisés**, pas nécessairement sur toute la blockchain.

---

# 13. MODE C — Serveur personnel

Plus tard, Alice achète son propre serveur.

Elle installe :

```text
ARTCB Domain Node
```

puis :

```text
Ajouter ce serveur à ORG ACME
```

Le serveur doit prouver :

```text
Node Identity
      +
Domain Authorization
      +
Founder Authorization
```

et seulement après :

```text
synchronisation du domaine
```

C'est beaucoup plus sécurisé qu'un simple téléchargement du fichier.

---

# 14. MODE D — Hybride

C'est celui que je recommande pour ARTCB.

Par exemple :

```text
             ORG ACME
                 │
       ┌─────────┼─────────┐
       │         │         │
    Node ARTCB  Node ARTCB  Serveur Alice
       │         │         │
       └─────────┴─────────┘
             domaine
```

Avec par exemple :

```text
3 replicas
2 nécessaires pour récupération
1 serveur propriétaire
```

Ainsi :

* Alice n'a pas besoin d'héberger elle-même ;
* ARTCB peut assurer la disponibilité ;
* Alice peut reprendre le contrôle ;
* elle peut migrer vers son propre serveur ;
* la disparition d'un nœud ne détruit pas l'organisation.

---

# 15. Mais il y a une subtilité cryptographique très importante

Il ne faut surtout pas faire :

```text
Node A possède la clé privée d'Alice
```

ou :

```text
Node A possède la clé de contrôle de l'organisation
```

Non.

Le modèle correct est :

```text
Wallet Alice
     │
     ▼
Founder signature
     │
     ▼
ORG GENESIS
```

Le serveur possède :

```text
copie du domaine
```

mais pas :

```text
clé souveraine du fondateur
```

C'est cohérent avec le modèle déjà utilisé dans les routes de groupe : l'identité réelle est résolue depuis la session/API key/wallet et non simplement acceptée depuis le JSON envoyé par le client.

---

# 16. Le transfert vers son propre serveur devrait donc être une migration cryptographique

Exemple.

Alice crée :

```text
ORG ACME
```

sur Node A.

Six mois plus tard :

```text
Alice installe son propre serveur
```

Elle ne devrait pas faire :

```text
copier orgs.json
```

Je recommande :

```text
Nouveau serveur
       │
       │ demande d'adhésion au domaine
       ▼
Domain Controller
       │
       │ challenge
       ▼
Wallet Alice
       │
       │ signature
       ▼
autorisation
       │
       ▼
transfert chiffré du domaine
       │
       ▼
validation du hash
       │
       ▼
nouveau Domain Node
```

Et le nouveau serveur calcule :

```text
hash(local_genesis) == genesis_hash_committed
```

Si oui :

```text
VALID
```

Sinon :

```text
INVALID / CORRUPTED
```

---

# 17. C'est exactement là que le `content_hash` actuel est utile

Le code actuel calcule déjà un hash canonique du Genesis.

Pour l'organisation :

```text
canonical_hash(constitution_payload())
```

puis le stocke dans :

```text
content_hash
```

et génère un commitment public contenant :

```text
kind
domain_id
content_hash
parent_id
issuer
issued_at
```

C'est une très bonne base pour réaliser la migration.

---

# 18. Il faut cependant distinguer « commitment créé » et « commitment réellement blockchain »

Et là je veux être très précis.

Dans le code que j'ai vérifié, `GenesisStore` écrit actuellement le commitment dans :

```text
commitments.jsonl
```

La matrice décrit le commitment comme une donnée que le réseau peut connaître, mais **ce code seul ne me permet pas de certifier que chaque création d'organisation est actuellement inscrite comme transaction consensuelle dans la blockchain globale**.

C'est une distinction importante.

Il y a donc deux choses :

```text
A. commitment local
```

et

```text
B. commitment effectivement finalisé dans GLOBAL CONSENSUS
```

Il faut vérifier/garantir le passage A → B.

---

# 19. Donc je classerais l'état actuel ainsi

| Fonction                                                               | État actuel                                         |
| ---------------------------------------------------------------------- | --------------------------------------------------- |
| Utilisateur sans serveur peut créer une organisation                   | **Oui**                                             |
| Création via interface/API                                             | **Oui**                                             |
| Genesis ORG local                                                      | **Oui**                                             |
| Genesis GROUP local                                                    | **Oui**                                             |
| Founder cryptographiquement identifié                                  | **Oui, base présente**                              |
| Hash du Genesis                                                        | **Oui**                                             |
| Commitment public                                                      | **Oui, mécanisme présent**                          |
| Séparation Genesis global / ORG / GROUP                                | **Oui**                                             |
| Organisation = propriété du serveur                                    | **Non, ce ne doit pas être le modèle**              |
| Migration automatique vers serveur personnel                           | **À intégrer**                                      |
| Domain manifest/routing                                                | **À renforcer/intégrer**                            |
| Réplication contrôlée du domaine                                       | **Architecture prévue, implémentation à certifier** |
| Recovery indépendant du nœud initial                                   | **À intégrer/valider**                              |
| Preuve que le commitment est réellement finalisé sur la chaîne globale | **À auditer**                                       |
| Export/import sécurisé d'un domaine                                    | **À intégrer**                                      |

---

# 20. Le point à corriger dans notre modèle mental

Il faut maintenant abandonner ce schéma :

```text
NODE = DOMAIN
```

et utiliser :

```text
NODE = infrastructure capable d'héberger un ou plusieurs DOMAINES
```

C'est beaucoup plus juste.

Par exemple :

```text
                    NODE A
                     │
          ┌──────────┼──────────┐
          │          │          │
       ORG-A       ORG-B      GROUP-C
       domain      domain      domain
```

Un même serveur peut donc potentiellement héberger plusieurs domaines.

Inversement :

```text
             ORG-A
               │
       ┌───────┼───────┐
       │       │       │
     Node A  Node B  Node D
```

Un même domaine peut être réparti sur plusieurs nœuds.

**C'est cette relation qu'ARTCB doit avoir à terme.**

---

# 21. Et cela résout ton problème initial

Ton utilisateur :

```text
Alice
```

n'a rien installé.

Elle crée :

```text
ORG ACME
```

ARTCB peut lui répondre :

```text
Organisation créée

Organization ID:
org_8F29...

Genesis hash:
a81c...

Founder:
wallet_alice

Domain:
domain_73...

Storage:
ARTCB managed

Domain nodes:
Node Paris
Node Frankfurt

Recovery:
enabled
```

Alice n'a donc pas besoin de comprendre :

```text
JSON
filesystem
GenesisStore
P2P
nœud
```

Elle possède simplement :

```text
WALLET
   +
ORG_ID
   +
GENESIS_HASH
   +
DOMAIN_ID
```

---

# 22. Et quand elle voudra reprendre son domaine

Elle installe son serveur :

```text
ARTCB Node
```

puis :

```text
Importer une organisation existante
```

Elle fournit/autorise :

```text
ORG_ID
```

Le système demande une signature au wallet :

```text
Sign:
"Authorize domain migration
 for ORG_ACME
 to NODE_X"
```

Alice signe.

Puis :

```text
NODE_X
   │
   ▼
preuve de propriété
   │
   ▼
récupération des fragments/données
   │
   ▼
validation Genesis hash
   │
   ▼
activation
```

Ainsi, **le serveur n'est jamais la source de vérité de la propriété**.

---

# 23. Ma recommandation architecturale pour ARTCB

Je ferais évoluer le système vers cette architecture :

```text
                     GLOBAL CONSENSUS
                            │
            ┌───────────────┴───────────────┐
            │                               │
      ORG COMMITMENT                  GROUP COMMITMENT
       ID + HASH                         ID + HASH
            │                               │
            └───────────────┬───────────────┘
                            │
                     DOMAIN REGISTRY
                            │
             ┌──────────────┼──────────────┐
             │              │              │
          Domain A       Domain B       Domain C
             │
        ┌────┼────┐
        │    │    │
      Node1 Node2 Node7
```

Et chaque domaine possède :

```text
Domain Manifest
       │
       ├── domain_id
       ├── owner/founder
       ├── genesis_hash
       ├── parent_id
       ├── authorized_nodes
       ├── replication_policy
       ├── recovery_policy
       ├── encryption policy
       └── version
```

---

# 24. Et surtout : ne pas mettre tout dans le Genesis

Le code actuel a déjà une bonne séparation conceptuelle :

```text
GENESIS
    = constitution

POLICY TX
    = GRANT / REVOKE / DELEGATE

MEMBERS
    = domaine du groupe

RESOURCE
    = données privées
```

Le fichier `genesis.py` précise explicitement que le Genesis est la **constitution**, pas la base de permissions.

C'est une très bonne direction.

Il faut donc éviter de transformer le Genesis en énorme fichier contenant :

```text
tous les membres
tous les documents
toutes les transactions
toutes les clés
```

---

# 25. Le scénario que je considère le plus solide

Pour ARTCB, je choisirais finalement :

### Création

```text
Utilisateur
    ↓
Wallet
    ↓
ARTCB Web/API
    ↓
création ORG
    ↓
ORG Genesis
    ↓
hash
    ↓
global commitment
    ↓
Domain Registry
    ↓
2+ Domain Nodes
```

### Utilisation normale

```text
Utilisateur
    ↓
API
    ↓
Domain Router
    ↓
Domain Node autorisé
    ↓
ORG/GROUP
```

### Migration

```text
Utilisateur
    ↓
nouveau serveur
    ↓
signature Founder
    ↓
Domain Registry
    ↓
preuve d'autorisation
    ↓
réplication
    ↓
hash verification
    ↓
nouveau Domain Node
```

### Perte d'un serveur

```text
Node A ❌

        ↓

Node B ─────── Node C
        │
        ▼
     Domaine
        │
        ▼
continuité
```

C'est **beaucoup plus robuste** que de considérer le serveur initial comme propriétaire.

---

# 26. Conclusion très concrète

Tu avais en réalité identifié **un trou architectural important** dans notre discussion précédente.

### Ce qui est déjà correctement posé

Le code actuel a déjà :

* séparation **GLOBAL / ORG / GROUP / USER** ;
* Genesis ORG local ;
* Genesis GROUP local ;
* `organization_id` / `group_id` ;
* identité du fondateur ;
* hash canonique ;
* commitments publics ;
* séparation des données privées et publiques ;
* modèle de réplication par domaine.

### Ce qu'il faut maintenant rendre réellement opérationnel

Il manque surtout la couche :

> **« Mon domaine m'appartient cryptographiquement, indépendamment du nœud qui l'héberge. »**

Donc je recommande d'ajouter :

1. **Domain ID**
2. **Domain Manifest**
3. **Domain Registry**
4. **Founder-controlled recovery**
5. **liste des Domain Nodes autorisés**
6. **réplication contrôlée**
7. **export/import signé**
8. **migration de domaine**
9. **vérification `Genesis hash` après migration**
10. **preuve claire que le commitment est effectivement finalisé dans le consensus global**
11. **interface utilisateur permettant de choisir : ARTCB managed / nœud personnel / hybride**
12. **mécanisme de récupération si le premier serveur disparaît**

Et surtout, la règle architecturale devrait devenir :

> **Un nœud héberge un domaine ; il ne possède pas le domaine.**

C'est cette règle qui permet à quelqu'un qui n'a **aucun serveur et aucune installation ARTCB** de créer une organisation aujourd'hui, puis éventuellement de **récupérer cette même organisation sur son propre serveur demain**, sans casser son identité, son Genesis, son historique ou son autorité.

[Dépôt ARTCB sur GitHub](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

**Expertises mobilisées ici :** architecture blockchain distribuée, stockage/réplication P2P, identité cryptographique, contrôle d'accès, gestion de domaines, migration de données et conception de systèmes multi-nœuds.

Le point que je considère prioritaire maintenant est **l'audit concret du `Domain Registry / routing / réplication` dans `main`**, car c'est lui qui permettra de déterminer si ce que `domains.py` décrit comme architecture est déjà réellement exécuté par les quatre serveurs, ou seulement défini comme politique.


Oui. J’ai repris le **rapport 217 directement dans GitHub**, puis vérifié la pièce centrale du mécanisme dans `src/artcb/authz/domains.py` sur le SHA `8ff5ba5e512d71a34385803a3d60618c2bd5ac89`. Je vais donc distinguer ce qui est **réellement vérifié**, ce que cela signifie techniquement, et ce qui reste à faire.

## 1. Le point essentiel : il y a bien 4 niveaux différents

Le code définit explicitement quatre choses différentes portant le terme « Genesis » : le **Global Genesis**, l’**ORG Genesis**, le **GROUP Genesis**, puis les données utilisateur/ressources privées qui **ne sont pas un Genesis blockchain**.

La représentation la plus simple est :

```text
                         ARTCB
                           │
                    GLOBAL GENESIS
                           │
             ┌─────────────┴─────────────┐
             │                           │
          ORG A                       ORG B
       ORG GENESIS                 ORG GENESIS
             │
       ┌─────┴─────┐
       │           │
    GROUP C     GROUP D
    Genesis     Genesis
       │
    membres
       │
   ressources
   privées
```

Mais il faut surtout comprendre que **ces objets n'ont pas le même niveau de réplication**.

---

# 2. Le Global Genesis

C'est le Genesis que tu connaissais déjà.

Il contient la constitution fondamentale d'ARTCB :

* règles du consensus ;
* PoL ;
* supply ;
* paramètres fondamentaux du protocole.

Il doit être identique sur les nœuds de consensus.

Le code classe donc :

> `GLOBAL_GENESIS → all_consensus_nodes`

Autrement dit :

**OVH1 = OVH2 = AWS3 = OVH4**

doivent comprendre la même constitution protocolaire.

Sinon, ils pourraient avoir des règles différentes pour décider quel bloc est valide.

---

# 3. ORG Genesis : ce n'est PAS un deuxième blockchain Genesis

C'est ici que la distinction devient importante.

Pour une organisation A, on a :

```text
ORG A
 │
 ├── ORG Genesis
 │
 ├── politiques
 │
 ├── utilisateurs
 │
 └── ressources privées
```

Le **corps** du Genesis ORG reste dans le domaine de l'organisation.

Le réseau global ne reçoit qu'un engagement cryptographique :

```text
ORG A
   ↓
content_hash
```

Le code décrit précisément cette séparation :

```text
ORG_GENESIS_HASH
    replication = all_consensus_nodes

ORG_GENESIS_BODY
    replication = org_domain_nodes
```

### Exemple concret

Imaginons :

```text
ORG_A
fondateur = C1
politique = ...
agent_limit = ...
```

Le domaine possède le contenu.

Le réseau global connaît quelque chose du genre :

```json
{
  "kind": "org",
  "domain_id": "ORG_A",
  "content_hash": "abc123..."
}
```

Donc :

### Le réseau sait :

> « Une constitution ORG_A existe et son empreinte cryptographique est X. »

### Le réseau ne sait pas nécessairement :

> « Voici tout le contenu de la constitution ORG_A. »

C'est une distinction fondamentale entre **existence vérifiable** et **contenu confidentiel**.

---

# 4. GROUP Genesis fonctionne sur le même principe

Pour un groupe C :

```text
ORG A
   │
   └── GROUP C
          │
          ├── GROUP Genesis
          ├── membres
          ├── politiques
          └── ressources
```

Le réseau global connaît :

```text
GROUP C
parent = ORG A
content_hash = XXXXX
```

Mais les membres ne sont pas envoyés au réseau public.

Le code définit :

```text
GROUP_GENESIS_HASH → all_consensus_nodes
GROUP_MEMBERS      → group_domain_nodes
```

Donc si C contient :

```text
C1
C2
C3
C4
```

le consensus n'obtient pas automatiquement :

```text
GROUP C = [C1,C2,C3,C4]
```

Il peut seulement connaître l'engagement cryptographique correspondant.

---

# 5. Et surtout : les membres ne sont PAS dans le Genesis

C'est une autre correction importante.

Le Genesis n'est pas :

```text
Genesis
 ├── C1 READ document X
 ├── C2 WRITE document X
 └── C3 ADMIN document X
```

Ce serait une mauvaise architecture pour des droits évolutifs.

Le système sépare :

```text
GENESIS
   ↓
constitution
   ↓
qui peut déléguer quoi
   ↓
POLICY TX
   ↓
GRANT / REVOKE / DELEGATE
```

Le code classe explicitement `POLICY_TX` comme :

> `grant_revoke_delegate`

et non comme Genesis.

### Pourquoi ?

Parce que :

```text
Genesis = constitution
Policy = état évolutif des permissions
```

Si C3 reçoit aujourd'hui :

```text
READ → Document X
```

et que demain on veut :

```text
REVOKE → C3
```

on ne touche pas au Genesis.

C'est exactement le comportement qu'on veut.

---

# 6. Maintenant la partie la plus importante : où sont réellement les fichiers ?

C'est ici qu'il faut éviter une confusion.

Le rapport indique actuellement :

```text
ORG Genesis body
    → domaine local

GROUP Genesis body
    → domaine local

GROUP members
    → domaine groupe

private resources
    → local

global hashes
    → visibilité consensus
```

Le rapport précise même les fichiers concernés :

```text
data/authz/orgs.json
data/authz/group_genesis.json
data/authz/policies.jsonl
```

Donc **non**, le Genesis ORG complet n'est pas actuellement copié automatiquement sur les quatre serveurs.

Et **non**, les quatre serveurs ne possèdent pas quatre copies identiques de toutes les organisations.

C'est un point que je considère comme essentiel à conserver dans la documentation du projet.

---

# 7. Ce que les 4 nœuds possèdent réellement

D'après le rapport 217 et le code :

| Donnée           |               OVH1 |               OVH2 |               AWS3 |               OVH4 |
| ---------------- | -----------------: | -----------------: | -----------------: | -----------------: |
| Global Genesis   |                Oui |                Oui |                Oui |                Oui |
| Hash ORG A       |                Oui |                Oui |                Oui |                Oui |
| Corps ORG A      | Pas nécessairement | Pas nécessairement | Pas nécessairement | Pas nécessairement |
| Hash GROUP C     |                Oui |                Oui |                Oui |                Oui |
| Membres GROUP C  |    Non globalement |    Non globalement |    Non globalement |    Non globalement |
| Document privé X |        Non via P2P |        Non via P2P |        Non via P2P |        Non via P2P |
| Bloc public      |          Oui / P2P |          Oui / P2P |          Oui / P2P |          Oui / P2P |

Le mécanisme de réplication est explicitement défini dans `REPLICATION_MATRIX`.

---

# 8. Pourquoi le hash est-il public ?

Parce qu'un hash permet de faire quelque chose de très intéressant.

Supposons que le Genesis ORG soit :

```text
{
   founder: C1,
   rules: ...,
   limits: ...
}
```

On calcule :

```text
SHA-256(canonical_json)
        ↓
A7F91C....
```

Le réseau conserve :

```text
ORG_A → A7F91C...
```

Plus tard, le domaine présente son Genesis.

On recalcule :

```text
SHA-256(Genesis présenté)
```

Si :

```text
hash_calculé == hash_enregistré
```

on sait que le contenu correspond à celui qui avait été engagé.

C'est ce que fait `canonical_hash()` : JSON déterministe, puis SHA-256.

---

# 9. Mais attention : le hash actuel n'est PAS encore un bloc blockchain

C'est l'une des limites importantes que j'ai vérifiées.

Aujourd'hui, le système utilise un :

```text
commitments.jsonl
```

et non encore un véritable :

```text
blocks.jsonl
```

avec un `append_block`.

Le rapport classe donc cela en **P-217-2**.

Cela signifie :

### Aujourd'hui

```text
Genesis ORG
     ↓
SHA-256
     ↓
commitments.jsonl
     ↓
API /authz/commitments
```

### Ce qui serait plus fort

```text
Genesis ORG
     ↓
SHA-256
     ↓
transaction publique
     ↓
bloc blockchain
     ↓
hauteur H
```

La deuxième architecture donne une preuve beaucoup plus forte de **l'ancrage temporel et global**.

Le rapport dit explicitement que cet ancrage dans `blocks.jsonl` reste à faire.

---

# 10. Autre limite : le corps ORG n'est actuellement pas répliqué sur plusieurs nœuds du domaine

C'est probablement **la nuance la plus importante** de tout le rapport.

Le modèle prévoit :

```text
ORG domain nodes
```

mais actuellement :

```text
1 nœud = le domaine
```

Donc on n'a pas encore :

```text
ORG A
 ├── Node A1
 ├── Node A2
 └── Node A3
```

avec le Genesis ORG complet répliqué entre A1/A2/A3.

Le rapport le reconnaît comme **P-217-3**.

Donc je ne qualifierais **pas encore** cela de véritable « shard privé distribué ».

---

# 11. Le privé n'est pas encore chiffré au repos

Autre distinction majeure.

Le système empêche désormais le P2P de transporter les données privées.

Mais cela ne signifie pas :

> « personne ne peut lire le fichier privé sur le serveur ».

Le rapport dit explicitement :

```text
private data
    ↓
local disk
    ↓
plaintext
```

Le chiffrement au repos est encore **non implémenté**.

Donc :

### Protection actuelle

```text
Internet
   X
P2P
   X
API anonyme
   X
```

mais :

```text
disque du serveur
   ↓
fichier privé
   ↓
encore lisible localement
```

C'est une différence entre **confidentialité réseau** et **confidentialité au repos**.

---

# 12. La vérification live des 4 nœuds est, elle, beaucoup plus solide

Sur le SHA :

`8ff5ba5e512d71a34385803a3d60618c2bd5ac89`

le rapport donne les quatre nœuds :

* OVH1
* OVH2
* AWS3
* OVH4

avec le même SHA court `8ff5ba5`, `certified=true`, et `p2p_syncs_private_blocks=false`.

Le test live indique également :

```text
GET /chain anonyme
→ 1 bloc public

POST /groups anonyme
→ 401

P2P
→ public uniquement
```

sur les quatre nœuds.

Cela valide une chose importante :

**la protection n'est pas uniquement présente dans pytest ; elle a été observée sur les instances live indiquées dans le rapport.**

---

# 13. Ce que cela signifie concrètement pour ton exemple

Prenons :

```text
ORG A
   └── GROUP C
          ├── C1
          ├── C2
          └── C3

Document X
```

### Le réseau global peut savoir :

```text
ORG A existe
hash = H_ORG

GROUP C existe
parent = ORG A
hash = H_GROUP
```

### Le domaine peut connaître :

```text
constitution ORG A
politiques ORG A
```

### Le groupe peut connaître :

```text
constitution GROUP C
C1
C2
C3
```

### Document X

reste privé et n'est pas propagé par le P2P public.

Le code définit justement `PRIVATE_RESOURCE` avec :

```text
replication = never_p2p
```

---

# 14. Ce qui est maintenant réellement sécurisé

Je séparerais le résultat en trois niveaux.

### 🟢 Corrigé et vérifié

* séparation Global/ORG/GROUP/User ;
* hash public sans contenu privé ;
* filtrage HTTP des données privées ;
* P2P limité au public ;
* création de groupe authentifiée ;
* contrôle de l'identité de l'acteur ;
* endpoint `CAN_I` ;
* quatre nœuds live sur le même SHA ;
* `certified=true` conservé.

Le rapport 217 donne ces éléments comme codés, testés et, pour les éléments concernés, vérifiés live.

### 🟠 Encore incomplet

1. **Chiffrement au repos.**
2. **Ancrage des commitments dans `blocks.jsonl`.**
3. **Réplication du corps ORG sur plusieurs nœuds du domaine.**
4. **Signature autonome du fichier Genesis.**

Ces quatre points sont explicitement listés P-217-1 à P-217-4.

---

# 15. Mon verdict technique

Je ne formulerais donc **pas** :

> « ARTCB possède maintenant des shards privés totalement distribués. »

Ce serait trop fort par rapport au code actuel.

Je formulerais plutôt :

> **ARTCB dispose maintenant d'une séparation architecturale réelle entre constitution globale, constitutions ORG/GROUP, politiques évolutives et ressources privées. Les nœuds de consensus peuvent vérifier publiquement l'existence et l'identité cryptographique d'un domaine sans recevoir son contenu privé, tandis que le P2P refuse les blocs non publics. La réplication multi-nœuds du contenu privé et son chiffrement au repos restent toutefois à implémenter.**

Cette formulation correspond beaucoup mieux à ce que le code et le rapport démontrent réellement.

## Et surtout, par rapport à ta question initiale

**Non : créer ORG A sur OVH1 ne signifie pas actuellement que le Genesis ORG complet est automatiquement copié sur OVH2, AWS3 et OVH4.**

Ce qui est destiné à être globalement visible est **le commitment/hash**, pas le corps.

Et pour GROUP C, même logique :

```text
                  GLOBAL
                    │
        ┌───────────┴───────────┐
        │                       │
     HASH ORG                HASH GROUP
        │                       │
        │                       │
   corps ORG               corps GROUP
   domaine ORG             domaine GROUP
        │                       │
        └──── ressources privées
                  │
              jamais P2P
```

C'est précisément cette distinction qui est maintenant codée dans `REPLICATION_MATRIX`, plutôt que simplement décrite dans la documentation.

**Expertises mobilisées ici :** architecture blockchain/distributed systems, cryptographie appliquée (hash/commitment), contrôle d'accès/ABAC-RBAC, réplication P2P, sécurité des données au repos et audit de déploiement.

Si tu veux aller au niveau suivant, le point que je recommande d'examiner maintenant est **le mécanisme exact de création d'un ORG et d'un GROUP : qui écrit quel fichier, sur quel nœud, avec quelle clé, puis comment le commitment arrive aux quatre nœuds**. C'est là qu'on pourra vérifier de bout en bout qu'il n'existe aucun chemin caché qui recopierait accidentellement le contenu privé.


Oui. J’ai repris le contrôle **directement sur le code GitHub**, l’historique des commits et les tests E2E de la version concernée, au lieu de considérer le rapport 218 comme une preuve suffisante.

Il y a toutefois une distinction importante : **je peux vérifier directement le code et les artefacts versionnés ; je ne peux pas, depuis cet environnement, établir une nouvelle connexion réussie aux quatre IP OVH `:8443`**. J’ai donc séparé ci-dessous **preuve code**, **preuve test**, **preuve live rapportée**, et **ce qui reste non vérifié par une nouvelle sonde réseau**.

---

# 1. État réellement trouvé sur GitHub

Le dépôt `vgactech/artcb` est public, non archivé, avec `main` comme branche par défaut. Mon accès GitHub est en lecture seule : je peux auditer le dépôt mais pas pousser de modification.

Le dernier commit de `main` que GitHub me retourne est bien :

```text
c0e26abc21039045ae362585157c7fbe39359544
```

Message :

```text
docs(218): mesures live ae5868f — Alice sur OVH1 seulement
```

Il fait suite à :

```text
ae5868f  build(218): rebuild frontend dist
bb28385  feat(218): Domain Registry — le nœud héberge, le fondateur possède
```

Donc **oui : la phase 218 existe réellement dans `main`**, et ce n'est pas uniquement un texte posé dans une conversation.

GitHub

[Dépôt ARTCB — vgactech/artcb](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

---

# 2. Le point principal est réellement implémenté

J'ai lu directement :

```text
src/artcb/authz/domains.py
src/artcb/authz/registry.py
src/artcb/authz/genesis.py
src/api/authz_routes.py
tests/test_e2e218_domain_registry.py
```

Et là, le résultat est beaucoup plus intéressant que le simple rapport.

Le code définit explicitement :

```text
GLOBAL GENESIS
ORG GENESIS
GROUP GENESIS
USER / RESOURCE
```

avec des règles de réplication différentes. Le `DOMAIN_BODY` est défini comme :

```text
org_domain_nodes
```

et le code précise explicitement :

> un nœud héberge le domaine, il ne le possède pas.

### Donc ton modèle est maintenant bien représenté :

```text
                 ARTCB GLOBAL
                      │
             constitution globale
                      │
          ┌───────────┴───────────┐
          │                       │
       DOMAIN A                DOMAIN B
          │                       │
       fondateur                fondateur
          │                       │
      wallet Alice             wallet Bob
          │
     hosting node
          │
         OVH1
```

**Le serveur est une infrastructure d'hébergement. Il n'est pas le propriétaire juridique/logique du domaine.**

C'est exactement la séparation que tu cherchais.

---

# 3. Mais j'ai trouvé une nuance importante dans le code

C'est ici que je corrige une partie de la formulation précédente.

Le code de `POST /authz/orgs` fait bien :

1. authentification du fondateur ;
2. création du `OrgGenesis` ;
3. calcul du `content_hash` ;
4. création du `DomainManifest` ;
5. enregistrement du `hosting_node_id` ;
6. enregistrement des `authorized_nodes` ;
7. création d'un commitment.

Le passage est directement visible dans `authz_routes.py`.

Mais le commitment n'est **pas encore un bloc blockchain global**.

Il est ajouté par :

```python
gate.genesis.commitments.append(...)
```

Et `CommitmentLog` écrit dans :

```text
commitments.jsonl
```

Le code de `genesis.py` confirme que ce journal est un fichier local append-only.

Donc il faut absolument distinguer :

```text
commitment
   ≠
blockchain block
```

### Actuellement

```text
ORG Genesis
     │
     ├── corps → stockage local
     │
     └── hash → commitments.jsonl local
                         │
                         X
                   pas encore
                 bloc global P2P
```

C'est une distinction **très importante pour la sécurité et la cohérence distribuée**.

---

# 4. Le manifeste du domaine est bien distinct du Genesis

Le `DomainManifest` contient notamment :

```text
domain_id
domain_type
subject_id
founder_address
genesis_hash
hosting_node_id
authorized_nodes
storage_mode
recovery_enabled
min_replicas
body_replicated
commitment_anchored_on_chain
node_owns_domain
```

Le code force explicitement :

```text
node_owns_domain = false
commitment_anchored_on_chain = false
```

même lorsqu'un nœud héberge le domaine.

Donc :

### Alice

```text
founder_address = wallet Alice
```

### OVH1

```text
hosting_node_id = OVH1
```

### Relation

```text
Alice ───────────── possède ─────────────► Domain
                                              ▲
                                              │ héberge
                                              │
                                             OVH1
```

et surtout :

```text
OVH1 ≠ propriétaire
```

---

# 5. Alice n'a effectivement pas besoin d'installer ARTCB

C'est maintenant vérifié au niveau du design **et du test**.

Le test E2E démarre un nœud :

```text
node-paris
```

puis crée un wallet Alice et utilise l'API authentifiée pour créer l'organisation.

Le test vérifie :

```text
founder_address == Alice
node_owns_domain == false
hosting_node_id == node-paris
domain_id commence par domain_
```

Il vérifie également :

```text
founder_address != hosting_node_id
```

Donc le protocole ne confond effectivement pas l'identité humaine et l'identité du serveur.

---

# 6. Le point encore plus important : `authorized_nodes`

Voici une subtilité que je veux que l'on conserve très clairement.

Supposons :

```text
Alice
  │
  ▼
ORG A
  │
  ├── hosting_node = OVH1
  │
  └── authorized_nodes = [OVH1, OVH2]
```

Cela **ne signifie PAS** :

```text
OVH1 ──copie automatique──► OVH2
```

Le code fait explicitement la distinction :

> autoriser un nœud n'est pas copier le corps.

`add_replica()` ajoute le nœud à `authorized_nodes`, mais maintient :

```text
body_replicated = false
```

jusqu'à un véritable import.

Et le test E2E vérifie précisément ce comportement.

---

# 7. Donc le scénario `hybrid` est différent de ce que le nom pourrait laisser penser

C'est probablement l'un des points les plus importants à verrouiller.

Si Alice fait :

```json
{
  "storage_mode": "hybrid",
  "authorized_nodes": ["node-b"]
}
```

le système peut avoir :

```text
OVH1
 └── ORG Alice
      ├── corps Genesis
      └── authorized_nodes
           └── OVH2
```

mais **OVH2 n'a toujours pas le corps**.

Il faut ensuite effectuer :

```text
export
   ↓
transfert du bundle
   ↓
import
   ↓
vérification SHA-256
   ↓
installation du corps
```

C'est exactement ce que vérifie le test :

```text
body_replicated = false
```

avant import, puis `true` après import.

---

# 8. La récupération est donc réellement conçue

Le bundle contient :

```text
manifest
genesis_body
policies
exported_at
exported_by
export_hash
```

Avant import, le code recalcule le hash du Genesis.

Si quelqu'un modifie :

```text
ACME
```

en :

```text
HACKED
```

le hash ne correspond plus.

Le test prévoit précisément cette attaque et attend :

```text
DomainHashMismatch
```

Et le test E2E attaque réellement le bundle avant import :

```text
ACME → HACKED
```

puis vérifie que l'import est refusé.

### C'est une bonne propriété.

Elle signifie :

```text
copie physique
     ≠
copie de confiance
```

Le nouveau nœud doit prouver :

```text
hash(corps reçu) == genesis_hash du manifeste
```

---

# 9. GROUP a également son propre domaine

Ce n'est pas uniquement ORG.

Le test crée :

```text
ORG A
   │
   └── Groupe X
```

et vérifie que le groupe possède également :

```text
domain_type = group
```

avec :

```text
node_owns_domain = false
```

Le système crée donc bien une identité de domaine distincte pour le groupe.

Et `genesis.py` confirme que le `GroupGenesis` contient notamment :

```text
group_id
parent_org
parent_group_id
founder_address
content_hash
```

Le groupe est donc constitutionnellement rattaché à son organisation ou éventuellement à son groupe parent.

---

# 10. Là où le système est encore incomplet

C'est ici que je ne veux surtout pas te dire « tout est terminé ».

## A. Pas encore de réplication P2P privée automatique

Le code dit explicitement :

```text
P2P_SYNCS_PRIVATE_BLOCKS = False
```

et le manifeste indique que le registre lui-même reste local.

Donc actuellement :

```text
OVH1
  │
  └── ORG Alice

OVH2
  └── rien

AWS3
  └── rien

OVH4
  └── rien
```

tant qu'il n'y a pas d'import.

---

# 11. B. Pas encore d'ancrage blockchain global du commitment

Le code est même très explicite :

```text
commitment_anchored_on_chain = false
```

Donc aujourd'hui :

```text
hash du Genesis
      ↓
commitments.jsonl
      ↓
local
```

et pas encore :

```text
hash du Genesis
      ↓
bloc ARTCB
      ↓
consensus
      ↓
4 nœuds
```

### C'est probablement la dette technique la plus importante de cette phase.

Parce que sans ancrage global, un nœud qui possède seulement son fichier local peut dire :

> « Je connais le domaine X. »

Mais les autres nœuds n'ont pas encore une preuve consensuelle indépendante disant :

> « Le réseau ARTCB a accepté l'existence du domaine X avec ce hash. »

---

# 12. C. Et j'ai trouvé une subtilité supplémentaire : double commitment

C'est important.

Lors de :

```text
create_org()
```

`GenesisStore.create_org()` ajoute déjà un commitment :

```text
kind = org
domain_id = organization_id
content_hash = ...
```

Puis `authz_routes._register_domain()` ajoute également :

```text
kind = domain
domain_id = manifest.domain_id
content_hash = ...
```

Donc nous avons potentiellement :

```text
commitment #1
kind = org
id = org_xxx
hash = H

commitment #2
kind = domain
id = domain_xxx
hash = H
```

Ce n'est pas nécessairement une faille : les deux identités représentent deux niveaux différents.

Mais **il faut décider explicitement si cette duplication est voulue**.

Sinon on risque plus tard :

```text
ORG registry
        +
DOMAIN registry
        +
GROUP registry
        ↓
plusieurs représentations d'un même événement
```

et donc des risques de divergence comptable/consensus.

---

# 13. Le test ne se contente pas de tester le chemin heureux

C'est un bon signe.

La suite E2E vérifie notamment :

| Test                      | Résultat attendu         |
| ------------------------- | ------------------------ |
| création ORG authentifiée | 200                      |
| création sans session     | 401                      |
| domaine public            | hash sans Genesis body   |
| accès anonyme au body     | 401                      |
| non-fondateur export      | 403                      |
| fondateur export          | 200                      |
| Genesis modifié           | rejet hash               |
| `authorized_nodes`        | pas de copie automatique |
| import valide             | accepté                  |
| import falsifié           | rejeté                   |
| GROUP                     | Domain Manifest créé     |
| mauvais storage mode      | 422                      |

Ces tests sont réellement présents dans `test_e2e218_domain_registry.py`.

---

# 14. Maintenant, concernant les « logs réels »

Ici je veux être particulièrement rigoureux.

Le dépôt contient le **rapport de la mesure live** et son commit affirme :

```text
Alice sur OVH1 seulement
domains=0 sur OVH2/AWS3/OVH4
```

Le rapport est cohérent avec le code et les tests.

Le commit `c0e26ab` lui-même porte ce résultat dans son message.

Mais je n'ai **pas retrouvé dans GitHub le fichier brut `scripts/run_live218_domain_registry.py` ni les logs bruts des quatre serveurs** via la recherche de code actuelle.

Et surtout, une tentative de connexion directe depuis mon environnement aux endpoints :

```text
152.228.144.34:8443
151.80.107.29:8443
51.44.222.232:8443
91.134.45.8:8443
```

n'a pas abouti.

Donc je ne vais pas transformer :

> « le rapport affirme que la sonde live a donné X »

en :

> « je viens de mesurer X moi-même sur les quatre serveurs ».

Ce serait méthodologiquement faux.

---

# 15. Mon verdict après lecture croisée

### Ce que je considère maintenant comme **fortement établi**

**1. Domain identity distincte du node identity**

```text
founder_address ≠ hosting_node_id
```

Oui.

**2. ORG Genesis local**

Oui.

**3. GROUP Genesis local**

Oui.

**4. Domain Manifest**

Oui.

**5. `domain_id` distinct**

Oui.

**6. Le serveur héberge mais ne possède pas**

Oui, explicitement codé et testé.

**7. Alice peut créer une ORG sans être elle-même un nœud**

Oui, démontré par le test.

**8. Un nœud autorisé n'obtient pas automatiquement le corps**

Oui.

**9. Export/import avec vérification cryptographique**

Oui.

**10. GROUP possède également un Domain Manifest**

Oui.

---

# 16. Ce qui n'est PAS encore démontré au niveau réseau

Il faut maintenir ces trois cases séparées :

| Fonction                            | État                                                 |
| ----------------------------------- | ---------------------------------------------------- |
| Code de la fonction                 | **présent**                                          |
| Test local/E2E                      | **présent**                                          |
| Exécution distribuée réelle 4 nœuds | **rapportée, mais pas re-sondée par moi maintenant** |

Et surtout :

| Fonction                                    | État actuel    |
| ------------------------------------------- | -------------- |
| Genesis global                              | oui            |
| ORG Genesis                                 | oui            |
| GROUP Genesis                               | oui            |
| Domain Manifest                             | oui            |
| stockage privé local                        | oui            |
| export/import                               | oui            |
| vérification SHA-256                        | oui            |
| réplication privée automatique              | **non**        |
| commitment dans `blocks.jsonl`              | **non**        |
| consensus global sur l'existence du domaine | **pas encore** |
| P2P privé du corps                          | **non**        |

---

# 17. Le schéma réel actuel

Je te recommande de considérer **ce schéma** comme la représentation correcte de l'architecture actuelle :

```text
                         ARTCB GLOBAL
                    ┌────────────────────┐
                    │ Global Genesis     │
                    │ protocole           │
                    └─────────┬──────────┘
                              │
                    pas encore d'ancrage
                    blockchain du domaine
                              │
                              ▼
                       Domain Manifest
                              │
             ┌────────────────┼────────────────┐
             │                │                │
          domain_id       founder          hash
             │             Alice              │
             │                                │
             └───────────────┬────────────────┘
                             │
                             ▼
                           OVH1
                    ┌─────────────────┐
                    │ ORG Genesis     │
                    │ privé/local     │
                    │                 │
                    │ groupes         │
                    │ policies        │
                    │ ressources      │
                    └─────────────────┘

             OVH2          AWS3          OVH4
              │             │              │
              └─────────────┴──────────────┘
                     pas de corps privé
```

Puis, si Alice décide réellement de répliquer :

```text
OVH1
 │
 │ export signé/fondateur
 │
 ▼
OVH2
 │
 │ verify genesis_hash
 │
 ▼
installation locale
```

Ce n'est **pas** encore :

```text
OVH1 ───── P2P automatique ─────► OVH2
```

---

# 18. Conclusion critique

Le changement 218 est donc **réel et substantiel**.

La phrase :

> **« Un nœud héberge ; le fondateur possède. »**

n'est plus seulement une idée d'architecture : **elle est maintenant matérialisée dans le code, le manifeste, les routes et les tests E2E.**

Mais il serait prématuré de dire :

> « ARTCB possède maintenant des domaines privés distribués et consensuels. »

Ce n'est **pas encore le cas**.

La situation exacte est :

```text
             IDENTITÉ
                │
                ▼
       Domain Manifest
                │
        ┌───────┴────────┐
        │                │
   propriétaire       hébergeur
      Alice              OVH1
        │                │
        └───────┬────────┘
                ▼
          Genesis body
             local
                │
                ▼
         commitments.jsonl
             local
                │
                X
          pas encore
       blocks.jsonl global
```

### Ma priorité technique suivante serait donc :

**P-218-2 : transformer le `public_commitment` local en véritable événement consensuel ARTCB, sans jamais mettre le Genesis privé, les membres ou les documents dans le bloc public.**

C'est précisément ce qui permettrait d'obtenir enfin :

```text
4 nœuds
   │
   ├── connaissent domain_id
   ├── connaissent founder
   ├── connaissent genesis_hash
   ├── connaissent parent
   │
   └── NE connaissent PAS le corps privé
```

avec, cette fois, une **preuve blockchain globale** de l'existence et de l'intégrité du domaine.

Et je garderais absolument la séparation :

```text
PUBLIC CONSENSUS
    = identité + hash + relation

PRIVATE DOMAIN
    = Genesis body + membres + documents + politiques privées
```

C'est la séparation architecturale la plus importante obtenue dans cette phase.


Oui. **C’est un mécanisme indispensable** si ARTCB doit être utilisable par des entreprises, associations, administrations, groupes privés, etc.

Le point fondamental est le suivant :

> **On ne doit pas transférer le Genesis de l’organisation. On transfère l’autorité de contrôle de l’organisation.**

Le Genesis de l’ORG reste historiquement le même ; son propriétaire/autorité peut évoluer par une opération de gouvernance vérifiable.

Les documents ARTCB vont déjà dans cette direction : le Genesis est conçu comme la **constitution** de l’organisation, tandis que les permissions évoluent ensuite par des transactions `GRANT / REVOKE / DELEGATE`.  Le réseau peut également conserver l’engagement cryptographique du Genesis sans nécessairement connaître les données privées de l’organisation. 

---

# 1. Première distinction : « propriétaire » ne veut pas toujours dire la même chose

Il faut absolument distinguer **la propriété juridique** et **l'autorité technique ARTCB**.

### Exemple Aline

Aline crée :

```text
ORG_ALINE
Entreprise XYZ
```

Aline est actuellement l'autorité de contrôle.

Mais juridiquement, l'organisation peut appartenir à :

```text
Entreprise XYZ
```

et non à Aline personnellement.

Aline peut simplement être :

```text
PDG
Directrice
Administratrice
Représentante légale
```

Cela donne deux situations très différentes.

### Situation 1 — Aline possède réellement l'entreprise

Elle vend l'entreprise à Bob.

Il faut alors transférer le contrôle de l'ORG à Bob ou, mieux, à la **nouvelle entité juridique propriétaire**.

### Situation 2 — Aline était seulement directrice

L'entreprise reste la propriété de l'association/société.

Aline quitte son poste et Bob devient directeur.

Dans ce cas :

> **on ne vend pas/transfère pas l'ORG.**

On remplace simplement **l'autorité représentative** de l'ORG.

C'est une différence extrêmement importante.

---

# 2. Architecture que je recommande pour ARTCB

Je ferais évoluer le modèle vers :

```text
                    ARTCB GLOBAL
                         │
                         ▼
                 ORG GENESIS
                         │
              ┌──────────┴──────────┐
              │                     │
        Organisation          Autorité actuelle
              │                     │
       groupes / données       Governance Keys
       / ressources
```

Le Genesis contient notamment :

```text
ORG_ID
création
constitution
règles de gouvernance
règles de délégation
règles de succession
règles de révocation
racines cryptographiques
```

Mais il ne devrait pas être modifié à chaque changement de directeur.

Le Genesis est la **constitution initiale**.

Les changements passent ensuite par des transactions de gouvernance.

---

# 3. Il faut donc introduire une transaction spéciale

Je recommande fortement un type :

```text
ORG_CONTROL_TRANSFER
```

ou :

```text
ORG_AUTHORITY_TRANSFER
```

Son rôle serait :

> « L'autorité actuellement légitime de ORG_X transfère le contrôle administratif à Y. »

Par exemple :

```text
ORG_X

ancienne autorité :
ALINE_KEY

nouvelle autorité :
BOB_KEY

type :
CONTROL_TRANSFER

raison :
SALE / SUCCESSION / DIRECTOR_CHANGE

version :
42

timestamp :
...

signature ancienne autorité :
SIG_ALINE

acceptation nouvelle autorité :
SIG_BOB
```

Et surtout :

```text
ORG_ID ne change PAS
```

---

# 4. Pourquoi ne faut-il surtout pas créer une nouvelle ORG ?

Supposons :

```text
ORG_XYZ
```

créée par Aline en 2026.

Elle possède déjà :

```text
10 groupes
50 utilisateurs
4 000 documents
historique
transactions
politiques
agents
wallets
ressources
```

Si Aline vend l'entreprise à Bob, il serait catastrophique de faire :

```text
ORG_XYZ → supprimer

ORG_BOB → créer
```

Parce qu'on perdrait la continuité logique.

Il faudrait alors transférer :

```text
documents
groupes
utilisateurs
historique
permissions
agents
ressources
identifiants
```

et cela créerait énormément de problèmes.

---

# 5. La bonne solution : même ORG, nouvelle autorité

On fait :

```text
                 ORG_XYZ
                    │
          ┌─────────┴─────────┐
          │                   │
     historique          nouvelle autorité
          │                   │
      Aline                 Bob
```

Avant :

```text
ORG_XYZ
ROOT = ALINE
```

Après :

```text
ORG_XYZ
ROOT = BOB
```

Mais :

```text
ORG_ID = ORG_XYZ
```

reste identique.

Les groupes restent identiques.

Les données restent identiques.

L'historique reste identique.

---

# 6. Exemple complet : Aline vend son entreprise à Bob

## Étape 1 — situation initiale

```text
Entreprise XYZ

ORG_ID = ORG-123

Autorité :
Aline

Groupes :
 ├── Direction
 ├── Finance
 ├── RH
 └── Production
```

Aline contrôle actuellement l'ORG.

---

## Étape 2 — vente

Juridiquement :

```text
Aline
   ↓
vente
   ↓
Bob
```

Mais ARTCB ne devrait pas simplement accepter :

```text
Bob dit :
"Je suis le nouveau propriétaire."
```

Sinon n'importe qui pourrait essayer de prendre le contrôle.

Il faut une **preuve d'autorité**.

---

# 7. Il faut donc une authentification forte du transfert

Je recommande :

```text
Ancienne autorité
       +
Nouvelle autorité
       +
preuve de succession/transfert
       ↓
ORG_CONTROL_TRANSFER
```

Par exemple :

```text
Aline signe
       │
       ▼
transfert vers Bob
       │
       ▼
Bob accepte
       │
       ▼
ARTCB valide
       │
       ▼
Bob devient autorité
```

Cela ressemble davantage à une **cession cryptographique de contrôle** qu'à un simple changement de nom.

---

# 8. Et je recommande encore mieux : une autorité multisignature

Il ne faudrait surtout pas que l'organisation soit contrôlée par une seule clé privée.

Par exemple :

```text
ORG XYZ

Governance:
3-of-5
```

Cela signifie :

> 3 signatures parmi 5 sont nécessaires pour effectuer une opération critique.

Exemple :

```text
Aline
Directeur financier
Administrateur juridique
Conseil 1
Conseil 2
```

Pour transférer l'ORG :

```text
Aline       ✓
Conseil 1   ✓
Conseil 2   ✓

= 3 signatures

TRANSFER ACCEPTÉ
```

Même si Aline disparaît ensuite, l'ORG n'est pas prisonnière de sa clé.

---

# 9. C'est particulièrement important pour les associations

Prenons ton exemple de Bob.

```text
Association ABC

Bob = directeur
```

Bob crée l'ORG :

```text
ORG_ABC
```

Mais juridiquement :

```text
ORG_ABC
    appartient à
Association ABC
```

Bob n'est que le représentant.

Donc lorsque Bob quitte son poste :

```text
Bob
 ↓
directeur sortant

Alice
 ↓
nouvelle directrice
```

On ne devrait **pas** faire :

```text
ORG_BOB → Alice
```

On devrait faire :

```text
ORG_ABC
 │
 ├── Association ABC
 │
 ├── ancien représentant : Bob
 │
 └── nouveau représentant : Alice
```

C'est beaucoup plus propre.

---

# 10. Il faut donc deux concepts dans ARTCB

Je recommande de ne pas avoir seulement :

```text
OWNER
```

mais au minimum :

```text
LEGAL_OWNER
AUTHORIZED_CONTROLLER
```

### LEGAL_OWNER

C'est :

> l'entité juridiquement propriétaire de l'organisation.

Par exemple :

```text
Entreprise XYZ
Association ABC
Fondation DEF
Administration GHI
```

### AUTHORIZED_CONTROLLER

C'est :

> la personne ou le groupe de personnes actuellement autorisé à administrer techniquement l'ORG.

Par exemple :

```text
Aline
```

ou :

```text
Aline + Bob + Claire
```

avec une règle :

```text
2-of-3
```

---

# 11. Cela règle énormément de scénarios

## Scénario 1 — vente d'une entreprise

```text
Entreprise A
     ↓
vendue
     ↓
Entreprise B
```

Transfert :

```text
LEGAL_OWNER
A → B
```

Puis éventuellement :

```text
AUTHORIZED_CONTROLLER
Aline → Bob
```

---

## Scénario 2 — changement de PDG

L'entreprise ne change pas de propriétaire.

```text
LEGAL_OWNER
Entreprise XYZ
        │
        ├── Aline = ancien CEO
        └── Bob = nouveau CEO
```

Seul :

```text
AUTHORIZED_CONTROLLER
```

change.

---

# 12. Scénario 3 — décès du fondateur

C'est un cas que tu avais intérêt à prévoir dès maintenant.

Imagine :

```text
Aline = seule administratrice
```

Elle décède.

Si sa clé est nécessaire pour tout :

```text
Aline Key
   ↓
perdue
   ↓
ORG BLOQUÉE
```

C'est précisément ce qu'il faut éviter.

Le Genesis doit donc définir une **politique de succession**.

Par exemple :

```text
RECOVERY_POLICY

5 guardians
3 signatures nécessaires
```

ou :

```text
Conseil d'administration
2-of-3
```

ou encore :

```text
succession juridique
+
nouvelle clé
+
délai de sécurité
```

---

# 13. Scénario 4 — Aline perd sa clé

Même problème.

Il faut pouvoir dire :

```text
clé Aline compromise/perdue
        ↓
révocation
        ↓
nouvelle clé
        ↓
nouvelle autorité
```

Sans modifier :

```text
ORG_ID
Genesis historique
groupes
documents
historique
```

---

# 14. Scénario 5 — Aline est remplacée mais reste dans l'entreprise

Très important.

Avant :

```text
Aline
CEO
```

Après :

```text
Bob
CEO
Aline
employée
```

ARTCB doit pouvoir faire :

```text
Aline
ROLE = employee
```

et :

```text
Bob
ROLE = executive
```

Cela signifie que **changer le contrôle de l'ORG ne supprime pas automatiquement l'identité d'Aline de l'organisation**.

Ses anciens documents restent attribués à Aline.

Ses anciennes signatures restent valides historiquement.

Ses anciennes transactions restent dans l'historique.

Mais elle ne peut plus effectuer les opérations réservées au nouveau contrôleur.

---

# 15. C'est là que Genesis + Policy devient très puissant

Le modèle déjà décrit dans tes documents est exactement adapté à cela :

```text
GENESIS
   │
   │ constitution
   ▼
POLICY
   │
   ├── GRANT
   ├── REVOKE
   ├── DELEGATE
   └── TRANSFER
```

Le Genesis dit :

> « Voici les règles selon lesquelles l'autorité peut être transférée. »

La transaction dit :

> « Voici le transfert effectivement réalisé. »

Les permissions évolutives ne doivent donc pas être écrites définitivement dans le Genesis. Les documents ARTCB font déjà cette distinction entre Genesis/constitution et `POLICY_TX`. 

---

# 16. Et les groupes ?

C'est justement l'avantage.

Supposons :

```text
ORG_XYZ
│
├── GROUP_FINANCE
├── GROUP_RH
├── GROUP_ENGINEERING
│     ├── SUBGROUP_A
│     └── SUBGROUP_B
└── GROUP_DIRECTION
```

Aline transfère l'ORG à Bob.

On **ne transfère pas chaque groupe individuellement**.

Le lien reste :

```text
GROUP_FINANCE
      ↓
parent = ORG_XYZ
```

Donc :

```text
ORG_XYZ
ancienne autorité = Aline
nouvelle autorité = Bob
```

Tous les domaines enfants continuent d'appartenir à :

```text
ORG_XYZ
```

Le changement de l'autorité racine se propage selon les règles de gouvernance.

---

# 17. Attention : les administrateurs de groupes ne doivent pas devenir propriétaires de l'ORG

Supposons :

```text
ORG XYZ
│
├── Finance
│    └── Alice = admin
│
├── RH
│    └── Charles = admin
│
└── Engineering
     └── David = admin
```

Si Bob devient propriétaire/contrôleur de l'ORG :

```text
Bob
 ↓
ORG XYZ
```

cela ne signifie pas automatiquement :

```text
Bob
 ↓
Finance
RH
Engineering
```

Les délégations restent bornées.

La règle déjà étudiée est particulièrement importante ici :

$$
P_{child} \subseteq P_{parent}
$$

Autrement dit :

> **Une autorité enfant ne peut jamais recevoir plus de pouvoir que ce que son parent lui a délégué.** 

---

# 18. Je recommande également un délai de sécurité

Pour une opération aussi importante que :

```text
ORG_CONTROL_TRANSFER
```

je ne l'exécuterais pas instantanément.

Par exemple :

```text
J0
demande de transfert

J0 + validation
ancienne autorité signe

J0 + acceptation
nouvelle autorité signe

J0 + délai
fenêtre de contestation

J0 + N heures/jours
transfert définitif
```

Cela protège contre :

* clé compromise ;
* erreur humaine ;
* malware ;
* agent compromis ;
* signature volée ;
* attaque interne.

---

# 19. Il faut aussi prévoir « TRANSFER + REVOKE »

Au moment du transfert :

```text
Aline
```

ne doit pas automatiquement conserver :

```text
ORG_ADMIN
```

sauf si la nouvelle gouvernance le décide.

La transaction devrait donc pouvoir produire :

```text
OLD_CONTROLLER
    ↓
REVOKED

NEW_CONTROLLER
    ↓
ACTIVE
```

Mais son identité historique reste.

C'est-à-dire :

```text
Aline
ancienne administratrice
2026 → 2030

Bob
nouvel administrateur
2030 → ...
```

L'historique devient ainsi parfaitement auditable.

---

# 20. Il faut également prévoir la « délégation temporaire »

Autre scénario que tu n'as pas mentionné mais qui est très utile.

Aline part en congé pendant 3 mois.

Elle ne veut pas transférer l'ORG.

Elle fait :

```text
Aline
  │
  └── DELEGATE
          ↓
        Bob
```

avec :

```text
début : 01/01
fin : 31/03
permissions :
    administration
    groupe RH
    agents
```

Puis automatiquement :

```text
31/03
   ↓
DELEGATION EXPIRE
   ↓
Aline récupère le contrôle
```

C'est très différent d'un transfert permanent.

---

# 21. Autre scénario : transfert partiel

Encore un cas important.

Aline reste propriétaire mais transfère :

```text
GROUP_ENGINEERING
```

à une filiale.

On ne transfère donc pas :

```text
ORG_XYZ
```

mais :

```text
SUBDOMAIN_TRANSFER
```

Par exemple :

```text
ORG_XYZ
│
├── Finance
├── RH
└── Engineering
        ↓
      FILIALE_X
```

Il faut alors une opération différente :

```text
DOMAIN_TRANSFER
```

avec des règles extrêmement strictes.

---

# 22. Autre scénario : fusion de deux entreprises

Par exemple :

```text
Entreprise A
ORG_A

Entreprise B
ORG_B
```

fusionnent.

Il faut pouvoir avoir :

```text
ORG_A
     \
      → ORG_AB
     /
ORG_B
```

Mais **je déconseille de supprimer immédiatement ORG_A et ORG_B**.

Il vaut mieux conserver :

```text
ORG_A
status = merged
successor = ORG_AB
```

et :

```text
ORG_B
status = merged
successor = ORG_AB
```

Ainsi l'historique cryptographique reste intact.

---

# 23. Autre scénario : séparation / spin-off

L'inverse est également nécessaire.

Une entreprise :

```text
ORG_A
```

possède :

```text
GROUP_X
GROUP_Y
GROUP_Z
```

Puis `GROUP_Z` devient une société indépendante.

On peut créer :

```text
ORG_NEW
```

avec :

```text
successor_of = ORG_A
```

et transférer **uniquement les ressources explicitement autorisées**.

C'est beaucoup plus complexe qu'un simple changement de propriétaire.

Il faut notamment décider :

```text
qui possède les documents ?
qui possède les clés ?
qui conserve les historiques ?
qui garde les utilisateurs ?
quels agents sont transférés ?
quels wallets ?
quels contrats ?
```

---

# 24. Autre scénario : faillite / liquidation

Il faut également prévoir :

```text
ORG
 ↓
liquidation
```

L'ORG ne doit pas nécessairement être supprimée.

On peut avoir :

```text
ACTIVE
   ↓
LIQUIDATION
   ↓
FROZEN
   ↓
CLOSED
```

Avec conservation de l'historique.

---

# 25. Autre scénario : gouvernement / association / entreprise à gouvernance collective

C'est probablement là que le modèle multisignature devient le plus intéressant.

Exemple :

```text
Association ABC
```

Genesis :

```text
Governance = BOARD
Threshold = 3/5
```

Les cinq membres du conseil sont :

```text
B1
B2
B3
B4
B5
```

Pour changer le directeur :

```text
B1 ✓
B2 ✓
B4 ✓

3/5
```

Puis :

```text
Bob
↓
révoqué comme représentant

Alice
↓
nouvelle représentante
```

L'ORG reste :

```text
Association ABC
```

Elle n'appartient pas personnellement à Bob.

---

# 26. Il faut donc que le Genesis de l'ORG prévoie sa propre constitution

Je recommande quelque chose de ce genre :

```text
ORG GENESIS
│
├── org_id
│
├── legal_entity
│
├── governance_model
│
├── initial_authority
│
├── governance_keys
│
├── threshold
│
├── succession_policy
│
├── recovery_policy
│
├── transfer_policy
│
├── delegation_policy
│
├── revocation_policy
│
├── child_domain_policy
│
└── cryptographic_roots
```

C'est cohérent avec le rôle constitutionnel déjà défini pour l'ORG Genesis : définir l'autorité, les règles de gouvernance, les délégations et les limites. 

---

# 27. Et le réseau global n'a pas besoin de connaître les documents privés

C'est un autre avantage important de ton architecture.

Le réseau peut connaître :

```text
ORG_ID
current_authority_root
policy_root
governance_version
transfer_sequence
content_hash
```

sans recevoir :

```text
contrat de vente
contrat de travail
documents RH
documents internes
données confidentielles
```

Le principe déjà décrit dans tes documents est :

```text
GLOBAL NETWORK
       │
       ├── ORG_ID
       ├── commitment/hash
       ├── policy_root
       └── preuves
```

tandis que le contenu privé reste dans le domaine concerné. 

---

# 28. Mais il y a une limite importante : la blockchain ne sait pas toute seule qui est juridiquement propriétaire

C'est probablement **le point le plus important à ne pas oublier**.

Si Bob écrit :

> « J'ai acheté l'entreprise. »

la blockchain ne peut pas automatiquement savoir si c'est vrai.

Il faut donc distinguer :

```text
PREUVE CRYPTOGRAPHIQUE
```

et :

```text
PREUVE JURIDIQUE
```

La cryptographie peut prouver :

> « La clé actuellement autorisée a signé cette opération. »

Elle ne peut pas, à elle seule, prouver :

> « Le tribunal français / registre du commerce reconnaît Bob comme propriétaire. »

Pour une organisation réelle, ARTCB devra donc éventuellement accepter une **preuve d'autorité externe** :

```text
registre légal
     ↓
document / attestation
     ↓
preuve vérifiable
     ↓
ARTCB
```

ou utiliser des attestations signées par des autorités reconnues.

---

# 29. Le modèle final que je recommande

Je résumerais toute la mécanique ainsi :

```text
                 ARTCB GLOBAL
                       │
                       ▼
                  ORG GENESIS
                       │
        ┌──────────────┴──────────────┐
        │                             │
   LEGAL OWNER                 GOVERNANCE
        │                             │
Entreprise ABC                  3-of-5 keys
                                      │
                           ┌──────────┴──────────┐
                           │                     │
                     Controller             Succession
                           │
                          Bob
                           │
              ┌────────────┼─────────────┐
              │            │             │
           GROUP A      GROUP B       GROUP C
```

Et les opérations deviennent :

```text
ORG_CREATE
ORG_POLICY_UPDATE
ORG_GRANT
ORG_REVOKE
ORG_DELEGATE

ORG_CONTROLLER_TRANSFER
ORG_CONTROLLER_ROTATE
ORG_CONTROLLER_REVOKE

ORG_SUCCESSION
ORG_RECOVERY

DOMAIN_TRANSFER
DOMAIN_MERGE
DOMAIN_SPLIT

ORG_FREEZE
ORG_UNFREEZE
ORG_CLOSE
```

---

# 30. Le point le plus important pour ARTCB

Je verrouillerais cette règle :

> **Une ORG possède une identité permanente. Son Genesis initial est immuable. Son contrôle est transférable selon la constitution de l'ORG. Le transfert modifie l'autorité active, pas l'identité ni l'histoire de l'organisation.**

Donc :

### Vente

```text
Aline
   ↓
vente
   ↓
Bob

ORG_ID reste identique
```

### Changement de directeur

```text
Association
   │
Bob → Alice

ORG_ID reste identique
LEGAL_OWNER reste identique
AUTHORITY change
```

### Décès

```text
clé perdue
   ↓
succession/recovery
   ↓
nouvelle autorité
```

### Congé

```text
DELEGATE
   ↓
Bob
   ↓
expiration automatique
```

### Fusion

```text
ORG_A + ORG_B
       ↓
    ORG_AB
```

### Filialisation

```text
GROUP_X
   ↓
nouvelle ORG
```

---

## 31. Et surtout : ce n'est pas encore entièrement implémenté dans l'état que nous avons audité

C'est important de ne pas confondre **architecture recommandée** et **fonctionnalité déjà opérationnelle**.

Les audits précédents indiquent que le modèle actuel possède déjà une première couche de domaines/groupes et de rôles, mais **pas encore toute cette constitution de gouvernance, succession, transfert d'autorité et délégation hiérarchique complète**. Le modèle actuel était notamment décrit comme beaucoup plus simple (`founder/admin/contributor/viewer`). 

Donc je ne considérerais pas encore :

```text
ORG_CONTROL_TRANSFER
SUCCESSION
LEGAL_OWNER
MULTISIG GOVERNANCE
DOMAIN_TRANSFER
```

comme des fonctionnalités certifiées du protocole actuel.

### Ma recommandation pour la prochaine spécification

Avant de coder, il faudrait définir précisément **le "ORG Governance Genesis"**, avec :

1. **qui est juridiquement propriétaire** ;
2. **qui contrôle techniquement l'ORG** ;
3. **comment le contrôle est transféré** ;
4. **qui peut déclencher un transfert** ;
5. **qui doit l'accepter** ;
6. **combien de signatures sont nécessaires** ;
7. **comment fonctionne la succession** ;
8. **comment fonctionne la récupération d'une clé perdue** ;
9. **comment un directeur est remplacé sans changer le propriétaire** ;
10. **comment transférer un groupe sans transférer toute l'ORG** ;
11. **comment gérer fusion, scission, liquidation et filiale** ;
12. **comment une preuve juridique externe peut être associée à la preuve cryptographique** ;
13. **comment les agents sont automatiquement réautorisés/révoqués après le changement** ;
14. **comment empêcher l'ancien contrôleur de conserver secrètement un accès** ;
15. **comment rendre toute l'opération historiquement et cryptographiquement auditable**.

C'est cette couche qui ferait passer ARTCB d'un simple système de **création d'ORG/groupes** à un véritable **système de gouvernance organisationnelle décentralisée et transférable**.

Et cela s'intègre très bien avec le principe déjà établi : **le Genesis définit la constitution ; les transactions de politique font évoluer les autorisations.** 
