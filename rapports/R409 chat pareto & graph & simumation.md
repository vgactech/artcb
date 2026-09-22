# AUDIT 1 — Architecture réelle du graphe ARTCB

**État audité : `main` actuel de `vgactech/artcb` au 21 septembre 2026**, commit `8c3ff3656521968de4684e371b4931734c814635` (`R407`). Le dépôt a été mis à jour aujourd’hui à 15:28 UTC. [Dépôt ARTCB — main actuel](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

### Expertises mobilisées

* architecture P2P et systèmes distribués ;
* théorie des graphes orientés ;
* protocoles de routage et découverte de pairs ;
* Kademlia/DHT ;
* Gossip/Gossipsub ;
* synchronisation blockchain ;
* analyse de code Python ;
* audit code ↔ tests ↔ artefacts ;
* résilience réseau ;
* neurosciences computationnelles et comparaison avec les réseaux biologiques.

---

# 1. Verdict immédiat

Il faut être très précis :

> **ARTCB possède aujourd'hui un réseau P2P fonctionnel avec découverte de pairs, synchronisation directe et propagation par gossip. Mais le “graphe complet directionnel” que tu décris n'est PAS actuellement implémenté comme une propriété garantie du protocole.**

Donc :

| Propriété demandée                                                  | État actuel                                                                      |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| A peut connaître B                                                  | **Oui**                                                                          |
| A peut établir une communication avec B                             | **Oui**                                                                          |
| B peut communiquer avec A                                           | **Oui**                                                                          |
| A→B et B→A sont deux objets de graphe indépendants                  | **Non démontré / non modélisé ainsi**                                            |
| Tous les nœuds sont automatiquement reliés à tous les autres        | **Non**                                                                          |
| Graphe complet `Kₙ` garanti                                         | **Non**                                                                          |
| Graphe orienté complet `Kₙ` avec `n(n−1)` arcs                      | **Non**                                                                          |
| A peut envoyer directement à Z si Z est un pair connu/connecté      | **Oui**                                                                          |
| A→B→O→Z est nécessaire si A et Z sont directement connectables      | **Non nécessaire**, mais dépend de la connectivité réelle                        |
| A→Z est garanti simplement parce que A et Z appartiennent au réseau | **Non**                                                                          |
| Z→A peut fonctionner directement                                    | **Oui si la connexion existe**, mais ce n'est pas une seconde arête indépendante |
| Propagation multi-sauts                                             | **Oui**                                                                          |
| Propagation sans chemin prédéfini unique                            | **Oui, via gossip/DHT**                                                          |
| Preuve que toutes les paires sont directement connectées            | **Absente**                                                                      |

C'est donc **une architecture P2P maillée/dynamique**, pas encore le **graphe complet directionnel explicite** de ton cahier des charges.

---

# 2. Ce qui est réellement présent dans le code

Il y a en fait **deux couches P2P différentes** dans ARTCB.

### Couche A — `PeerManager` / synchronisation HTTP

Le code maintient un registre local :

```text
data/p2p/peers.json
```

avec notamment :

```text
peer_id
host
port
kem_public_key
protocol_compatible
identity_fingerprint
capability_signed
last_seen
last_sync_ok
```

Le code actuel de `peers.py` crée donc une relation locale :

```text
A
│
└── connaît B
```

mais cela signifie :

> A possède une entrée décrivant B.

Cela ne signifie pas :

> tous les nœuds du réseau possèdent nécessairement une entrée A↔B.

C'est une distinction fondamentale.

---

# 3. Les communications directes existent réellement

Dans `sync.py`, ARTCB possède :

```text
push_to_peer(peer)
pull_from_peer(peer)
```

et utilise notamment :

```text
POST /api/v1/p2p/blocks/receive
GET  /api/v1/p2p/blocks/public
```

Le code possède également :

```text
sync_all_peers()
```

qui parcourt les pairs connus et effectue les opérations de synchronisation.

Les recherches dans le dépôt confirment explicitement cette structure : `sync_all_peers()` parcourt `self.peers.list_peers()` et effectue `pull_from_peer()` puis `push_to_peer()`. ([GitHub][1])

### Donc ton cas :

```text
A → Z
```

est techniquement possible **si Z est présent comme pair connu de A et que A peut joindre Z**.

Il n'est pas nécessaire de faire :

```text
A → B → O → Z
```

dans ce cas.

---

# 4. Mais attention : cela ne constitue pas encore ton graphe complet

C'est ici que se trouve le point critique.

Le code dit essentiellement :

```python
for peer in self.peers.list_peers():
    ...
```

Autrement dit :

> « Je communique directement avec les pairs que je connais. »

Ce n'est pas :

```text
for every node in network:
    create A → node
```

Il manque donc une propriété formelle de type :

$$
\forall A,B,\quad A\neq B
$$

$$
A\rightarrow B \in E
$$

avec :

$$
|E|=N(N-1)
$$

pour un graphe orienté complet de \(N\) nœuds.

---

# 5. Exemple avec 4 nœuds

Supposons :

```text
A
B
C
D
```

Ton architecture demandée signifie :

```text
A → B
B → A

A → C
C → A

A → D
D → A

B → C
C → B

B → D
D → B

C → D
D → C
```

Il y a :

$$
N(N-1)
$$

arcs directionnels.

Pour 4 nœuds :

$$
4(4-1)=12
$$

Donc **12 relations directionnelles**.

---

# 6. Ce que fait actuellement ARTCB

Le système actuel ressemble davantage à :

```text
        A
       / \
      B   C
       \ /
        D
```

ou :

```text
A ─── B
│     │
C ─── D
```

selon les pairs réellement connus/connectés.

Le nombre de connexions n'est donc pas mathématiquement imposé à :

$$
N(N-1)
$$

Il dépend de la découverte, de la configuration et des connexions effectivement établies.

---

# 7. Et il y a une deuxième architecture : Kademlia

C'est encore plus important.

ARTCB possède aujourd'hui `libp2p_node.py`.

Le code définit :

```text
KademliaDHT
```

avec :

```text
KADEMLIA_K = 20
KADEMLIA_ALPHA = 3
```

et **48 buckets Kademlia**.

Le DHT ne cherche donc volontairement pas à conserver tous les nœuds.

Il cherche plutôt les nœuds pertinents selon la distance XOR entre leurs identifiants.

Le code possède :

```text
find_closest(target_id)
```

qui retourne les pairs les plus proches.

Donc son modèle est :

```text
Nœud A
  │
  ├── quelques pairs
  ├── quelques autres pairs
  └── DHT
          ↓
       découverte
          ↓
       autres pairs
```

et non :

```text
A
├── B
├── C
├── D
├── E
├── F
└── ... tous les autres
```

---

# 8. C'est même volontaire dans Kademlia

Kademlia est conçu pour **ne pas construire un graphe complet**.

Pourquoi ?

Parce que si :

$$
N=1\,000\,000
$$

un graphe complet nécessiterait :

$$
N(N-1)
$$

soit environ :

$$
999\,999\,000\,000
$$

arcs directionnels.

Cela devient gigantesque.

Avec un réseau distribué à très grande échelle, chaque nœud ne veut donc généralement pas maintenir une connexion directe avec tout le monde.

Le modèle DHT cherche au contraire une structure beaucoup plus parcimonieuse.

---

# 9. Gossipsub change encore la situation

ARTCB possède également une couche de propagation de type Gossipsub.

Le code définit :

```text
GOSSIP_TTL = 64
```

et :

```python
_broadcast_block(...)
```

qui parcourt :

```python
self._connections.items()
```

Donc un bloc peut faire :

```text
A
 ↓
B
 ↓
C
 ↓
D
```

et être propagé progressivement.

Le code exclut même le nœud qui vient d'envoyer le message :

```text
exclude_id
```

afin d'éviter une boucle immédiate.

Le dépôt contient explicitement la logique :

```text
ANNOUNCE_BLOCK
        ↓
broadcast
        ↓
autres pairs connectés
```

[Code P2P ARTCB — libp2p_node.py](https://github.com/vgactech/artcb/blob/main/src/artcb/p2p/libp2p_node.py?utm_source=chatgpt.com)

---

# 10. Donc ton exemple A → B → O → Z est réellement possible

Oui.

Avec la couche gossip :

```text
A
 ↓
B
 ↓
O
 ↓
Z
```

l'information peut atteindre Z sans que A ait une connexion directe avec Z.

C'est exactement le principe de propagation multi-sauts.

Mais le point essentiel est :

> **Cela ne prouve pas qu'une liaison A→Z existe.**

C'est seulement :

$$
A\leadsto Z
$$

où `leadsto` signifie :

> « il existe un chemin entre A et Z ».

Ce n'est pas la même chose que :

$$
A\rightarrow Z
$$

---

# 11. C'est une distinction mathématique très importante

### Graphe avec chemin

```text
A → B → C → D
```

On peut avoir :

$$
A\leadsto D
$$

mais pas :

$$
A\rightarrow D
$$

### Graphe complet

```text
A → B
A → C
A → D
```

Ici :

$$
A\rightarrow D
$$

existe directement.

Ton objectif porte précisément sur cette deuxième propriété.

---

# 12. Question 7 : Z → A après réception

Ici il faut distinguer **transport** et **graphe logique**.

Avec le système TCP/libp2p actuel, une connexion établie entre A et Z est naturellement utilisable dans les deux directions.

Par exemple :

```text
A ───────── TCP ───────── Z
```

A peut envoyer :

```text
A → Z
```

et Z peut répondre sur cette même connexion :

```text
Z → A
```

Le code `LibP2PNode` maintient un `StreamWriter` pour une connexion et possède une boucle de lecture permettant de recevoir les messages de l'autre côté. [Code libp2p ARTCB](https://github.com/vgactech/artcb/blob/main/src/artcb/p2p/libp2p_node.py?utm_source=chatgpt.com)

### Mais cela ne correspond pas exactement à ton modèle.

Ton modèle demande :

```text
A → Z
Z → A
```

comme **deux arcs indépendants du graphe**.

L'implémentation actuelle fait plutôt :

```text
A ⇄ Z
```

avec une connexion de transport bidirectionnelle.

Donc :

> **la communication inverse existe, mais elle n'est pas modélisée comme une deuxième arête indépendante.**

C'est une différence conceptuelle majeure.

---

# 13. Autrement dit : ton analogie de l'autoroute n'est pas encore celle du code

Ton modèle :

```text
A ─────────→ Z
A ←───────── Z
```

signifie :

```text
Edge(A,Z)
Edge(Z,A)
```

Le code de transport fait plutôt :

```text
Connection(A,Z)
       ⇅
messages
```

Une seule connexion peut transporter :

```text
A → Z
Z → A
A → Z
Z → A
...
```

Donc **transport bidirectionnel ≠ deux arêtes indépendantes dans un graphe logique**.

---

# 14. Question 3 : toutes les liaisons sont-elles créées dès la constitution de la topologie ?

## Réponse : non.

Le système actuel possède :

```text
bootstrap
   ↓
discovery
   ↓
peer registration
   ↓
DHT
   ↓
connections
```

La documentation et le code indiquent que les nœuds récupèrent des seeds, découvrent des pairs et alimentent leurs structures locales. ([GitHub][1])

Il existe même actuellement un mécanisme `seed_discovery.py` destiné à résoudre un problème historique où les différents magasins de pairs n'étaient pas correctement reliés.

Le commentaire du code actuel explique notamment que les stores HTTP peers, libp2p DHT et gossip avaient historiquement été séparés. [Code seed discovery ARTCB](https://github.com/vgactech/artcb/blob/main/src/artcb/p2p/seed_discovery.py?utm_source=chatgpt.com)

Donc :

```text
topologie déclarée
≠
ensemble de toutes les connexions physiques établies
```

---

# 15. Question 4 : une liaison apparaît-elle lorsqu'une communication réelle a lieu ?

Il faut répondre **oui, en partie**, mais avec une nuance.

Il existe des relations de trois natures différentes :

### A. Entrée de découverte

```text
A connaît B
```

### B. Pair DHT

```text
A possède B dans sa table DHT
```

### C. Connexion active

```text
A ⇄ B
```

Ce sont trois niveaux différents.

Un nœud peut donc :

```text
connaître B
```

sans nécessairement avoir actuellement :

```text
connexion TCP A⇄B
```

Le code distingue bien les pairs DHT (`dht_peer_count`) et les connexions actives (`connected_peers`). [Code libp2p ARTCB — statut DHT/connexions](https://github.com/vgactech/artcb/blob/main/src/artcb/p2p/libp2p_node.py?utm_source=chatgpt.com)

---

# 16. Question 5 : préexistantes ou dynamiques ?

### Réponse : actuellement, elles sont principalement dynamiques.

Architecture actuelle :

```text
SEEDS
 ↓
DISCOVERY
 ↓
PEER REGISTRY
 ↓
DHT
 ↓
CONNECTION
 ↓
GOSSIP
```

Donc ce n'est pas :

```text
Genesis
 ↓
création obligatoire de N(N-1) liaisons
```

C'est plutôt :

```text
Genesis / configuration réseau
             ↓
        découverte
             ↓
       pairs connus
             ↓
       connexions utiles
             ↓
       propagation
```

---

# 17. Une preuve particulièrement importante dans le dépôt

Le rapport réseau `234` montre que les nœuds peuvent connaître les autres via seed discovery et que le réseau possède des problèmes distincts entre :

```text
discovery
```

et :

```text
P2P entrant
```

Le rapport signale notamment un cas où `ARTCB_NODE_PUBLIC_URL` n'était pas configuré et où le P2P entrant était donc impossible. ([GitHub][1])

Cela démontre bien qu'une entrée de découverte ne signifie pas automatiquement :

> « connexion directe garantie ».

---

# 18. Le système possède donc actuellement deux concepts qu'il ne faut surtout pas confondre

## Graphe logique

```text
A connaît B
```

## Graphe physique/transport

```text
A ⇄ B
```

## Graphe de propagation

```text
A → B → C → D
```

Ces trois graphes peuvent être différents.

C'est probablement **le point central de ton audit**.

---

# 19. Ce que ton architecture demanderait réellement

Je formaliserais ton objectif ainsi.

Soit :

$$
G=(V,E)
$$

où :

* \(V\) = ensemble des nœuds ;
* \(E\) = ensemble des liaisons directionnelles.

Tu demandes :

$$
\boxed{
\forall A,B\in V,\ A\neq B:
(A,B)\in E
}
$$

C'est un **graphe orienté complet**.

Le nombre de liaisons est :

$$
\boxed{
|E|=N(N-1)
}
$$

Pour :

|  Nœuds | Arcs directionnels |
| -----: | -----------------: |
|      2 |                  2 |
|      3 |                  6 |
|      4 |                 12 |
|     10 |                 90 |
|    100 |              9 900 |
|  1 000 |            999 000 |
| 10 000 |         99 990 000 |

C'est cette définition qu'il faudrait utiliser pour éviter toute ambiguïté future.

---

# 20. Et il faudrait distinguer quatre états d'une liaison

Je recommande de ne pas simplement stocker :

```text
A → B = true
```

mais :

```text
A
│
├── knows B
├── authorized_to_send B
├── direct_transport_available B
└── direct_transport_verified B
```

C'est-à-dire :

### État 1 — découverte

```text
KNOWN
```

A connaît l'existence de B.

### État 2 — autorisation

```text
AUTHORIZED
```

A est autorisé à communiquer avec B.

### État 3 — possibilité technique

```text
REACHABLE
```

A peut techniquement joindre B.

### État 4 — preuve réelle

```text
VERIFIED
```

A a réellement effectué une communication réussie avec B.

Cette séparation serait extrêmement utile pour ton architecture.

---

# 21. Il y a également une propriété que ton idée apporte et que le système actuel ne garantit pas

Supposons :

```text
A → B → O → Z
```

Avec ton graphe complet :

```text
A → Z
```

existe indépendamment.

Donc si :

```text
B tombe
```

le chemin :

```text
A → B → O → Z
```

disparaît.

Mais :

```text
A → Z
```

reste disponible.

C'est là que ton idée devient intéressante pour la **résilience**.

---

# 22. Mais attention à une conséquence importante

Un graphe complet ne réduit pas automatiquement le nombre de sauts **si le protocole continue à choisir des routes indirectes**.

Pour obtenir :

```text
A → Z
```

au lieu de :

```text
A → B → O → Z
```

il faut que le protocole puisse faire :

```text
1. identifier Z
2. vérifier que Z est autorisé
3. connaître son endpoint
4. établir/maintenir une connexion
5. envoyer directement
```

Donc :

$$
\text{graphe complet logique}
\neq
\text{communication directe automatique}
$$

Il faut les deux.

---

# 23. Et c'est là que Kademlia et ton idée divergent

Kademlia cherche :

```text
trouver efficacement le bon pair
```

Ton architecture cherche :

```text
posséder une liaison directe avec chaque pair autorisé
```

Ce sont deux philosophies différentes.

### Kademlia

```text
moins de connexions
+
routage intelligent
+
scalabilité
```

### Full mesh

```text
beaucoup de connexions
+
communication directe
+
redondance maximale
+
coût O(N²)
```

ARTCB utilise actuellement davantage la première philosophie.

---

# 24. Maintenant, ton hypothèse sur les réseaux neuronaux

Elle est intéressante, mais il faut la corriger scientifiquement.

Ton intuition :

> un réseau très interconnecté pourrait permettre à une information de devenir disponible ailleurs sans devoir reconstruire exactement le chemin inverse.

### Cette partie est raisonnable comme analogie.

Mais :

> **un réseau neuronal biologique n'est pas un graphe complet où chaque neurone possède une connexion directe vers tous les autres neurones.**

Ce serait faux.

---

# 25. Ce qui se passe réellement dans un cerveau

Un neurone reçoit des signaux de nombreux autres neurones :

```text
N1 ─┐
N2 ─┤
N3 ─┤
N4 ─┤
    ↓
   Neurone X
```

Puis X produit à son tour un signal vers d'autres neurones :

```text
X
├──→ Y
├──→ Z
└──→ W
```

L'information peut donc se propager :

```text
A
↓
B
↓
C
↓
D
```

mais également :

```text
A
├──→ B
├──→ C
└──→ D
```

et plusieurs chemins peuvent coexister.

---

# 26. Pourquoi cela peut donner une impression de communication globale

Parce que le cerveau possède énormément de **connectivité parallèle**.

Une information peut activer simultanément plusieurs populations :

```text
                 ┌→ B
                 ├→ C
A ───────────────┼→ D
                 ├→ E
                 └→ F
```

Puis :

```text
B ─┐
C ─┤
D ─┤
E ─┤
F ─┘
 ↓
autre population
```

On obtient donc une propagation distribuée.

Mais cela ne signifie pas :

```text
A → instantanément → Z
```

---

# 27. Il existe toujours une propagation physique

Les signaux neuronaux sont soumis :

* aux propriétés électriques des membranes ;
* aux potentiels d'action ;
* aux délais synaptiques ;
* à la conduction axonale ;
* à la structure des réseaux neuronaux.

Donc :

$$
A\rightarrow B\rightarrow C\rightarrow Z
$$

reste une propagation temporelle.

Il n'existe pas de téléportation biologique de l'information.

---

# 28. Ce qui est réellement intéressant pour ARTCB

L'analogie utile n'est donc pas :

> « ARTCB fonctionne comme un cerveau ».

Ce serait trop fort.

L'analogie plus rigoureuse serait :

> **ARTCB pourrait utiliser une architecture de propagation distribuée comportant plusieurs chemins parallèles et redondants, de manière analogue — à un niveau abstrait — à certaines propriétés de réseaux neuronaux fortement interconnectés.**

Cela est défendable.

---

# 29. Ce qui peut réellement être transposé à ARTCB

Je vois cinq propriétés intéressantes.

### 1. Redondance

```text
A → B → Z
A → C → Z
A → D → Z
```

Si B disparaît :

```text
A → C → Z
```

reste possible.

### 2. Propagation parallèle

```text
A
├──→ B
├──→ C
├──→ D
└──→ E
```

### 3. Multiples chemins

```text
A → B → Z
A → C → Z
A → D → E → Z
```

### 4. Tolérance aux pannes

La disparition d'un nœud ne détruit pas nécessairement l'information.

### 5. Agrégation

Plusieurs nœuds peuvent recevoir une information puis produire différentes interprétations/réponses.

Ce dernier point rejoint particulièrement ton architecture de KnowledgeID/raisonnements distribués déjà étudiée dans ARTCB. Les documents du projet distinguent déjà connaissance, relations, réutilisation et graphe évolutif. 

---

# 30. Mais il y a une différence fondamentale avec un cerveau

Dans un réseau informatique :

```text
message = données explicites
```

Dans un réseau biologique :

```text
activité neuronale
+
poids synaptiques
+
état biologique
+
dynamique temporelle
```

Un neurone ne reçoit pas simplement :

```text
"Bonjour, voici le message A"
```

et ne le transmet pas comme un routeur IP.

L'information est transformée pendant la propagation.

Donc :

```text
ARTCB réseau
```

et :

```text
réseau neuronal biologique
```

ne doivent pas être confondus.

---

# 31. Conclusion scientifique de l'hypothèse

Je classerais ton hypothèse ainsi :

| Proposition                                                           | Évaluation                            |
| --------------------------------------------------------------------- | ------------------------------------- |
| Les réseaux biologiques possèdent de nombreuses connexions parallèles | **Vrai**                              |
| Un cerveau est un graphe complet                                      | **Faux**                              |
| L'information peut emprunter plusieurs chemins                        | **Vrai**                              |
| Plusieurs populations peuvent être activées en parallèle              | **Vrai**                              |
| Une information arrive instantanément partout                         | **Faux**                              |
| Un réseau distribué peut offrir plusieurs chemins redondants          | **Vrai**                              |
| Cette propriété peut être transposée informatiquement                 | **Oui, comme principe architectural** |
| ARTCB actuel est déjà un graphe complet directionnel                  | **Non**                               |
| ARTCB actuel possède déjà propagation multi-sauts                     | **Oui**                               |
| ARTCB actuel garantit A→Z pour toute paire autorisée                  | **Non démontré**                      |

---

# 32. Le test qui manque maintenant dans ARTCB

Pour transformer ton idée en propriété **mesurable**, je créerais un test purement mathématique et réseau :

## Test `GRAPH-DIR-01`

Pour un réseau de \(N\) nœuds :

$$
ExpectedEdges=N(N-1)
$$

Pour chaque paire :

```text
A → B
B → A
```

tester :

```text
DISCOVERED
AUTHORIZED
REACHABLE
CONNECTED
MESSAGE_SENT
MESSAGE_RECEIVED
```

Exemple à 4 nœuds :

```text
A→B PASS
B→A PASS

A→C PASS
C→A PASS

A→D PASS
D→A PASS

B→C PASS
C→B PASS

B→D PASS
D→B PASS

C→D PASS
D→C PASS
```

Puis seulement :

```text
GRAPH-DIR-01 = PASS
```

si :

$$
12/12
$$

sont démontrées.

---

# 33. Et il faut faire un deuxième test séparé

Parce que le graphe complet ne suffit pas.

## `GRAPH-DIR-02`

Démontrer :

```text
A → Z
```

alors que :

```text
B
O
```

sont volontairement indisponibles.

Donc :

```text
A ─X→ B
A ─X→ O

A ─────────→ Z
              PASS
```

Puis le retour :

```text
Z ─────────→ A
```

sans :

```text
Z → O → B → A
```

Ce test permettrait de démontrer **exactement ta propriété**, et pas simplement la présence d'un système gossip.

---

# 34. Verdict final de l'AUDIT 1

### Ce qui est déjà réel

ARTCB possède actuellement :

```text
        SEEDS
          ↓
      DISCOVERY
          ↓
     PEER REGISTRY
          ↓
      KAD/DHT
          ↓
    CONNEXIONS P2P
          ↓
       GOSSIP
          ↓
     PROPAGATION
```

Le code contient bien les mécanismes correspondants, notamment Kademlia, connexions TCP, reconnexion, Gossipsub et synchronisation directe. [Architecture P2P ARTCB](https://github.com/vgactech/artcb/blob/main/src/artcb/p2p/libp2p_node.py?utm_source=chatgpt.com)

### Ce qui n'est pas encore démontré

```text
∀ A ≠ B :
A → B existe
ET
B → A existe
```

pour **toutes les paires autorisées**.

### Donc la réponse aux 8 questions est :

**1. Graphe complet ?**
**Non, pas au sens mathématique demandé.**

**2. A→B et B→A indépendantes ?**
**Non dans le modèle de transport actuel.** La connexion est bidirectionnelle ; les deux directions ne sont pas deux objets de graphe indépendants.

**3. Toutes les liaisons créées au départ ?**
**Non.** La découverte et la connexion sont dynamiques.

**4. Seulement après communication ?**
**Partiellement.** Il existe des entrées de découverte avant communication, puis des connexions actives après établissement.

**5. Préexistantes ou dynamiques ?**
**Principalement dynamiques.**

**6. A→Z possible directement ?**
**Oui si Z est connu/joignable directement.** Sinon la propagation peut passer par plusieurs nœuds.

**7. Z→A directement ?**
**Oui lorsqu'une connexion directe existe**, mais actuellement via la même connexion de transport bidirectionnelle, pas comme une seconde arête indépendante.

**8. Propriété démontrée dans le code ?**
**La communication P2P et la propagation sont réellement codées. Le graphe complet directionnel que tu demandes n'est pas implémenté/démontré.**

---

## Point architectural important

Je ne modifierais **rien dans le dépôt** à ce stade.

La prochaine étape logique est un **AUDIT 2 — “preuve expérimentale du graphe actuel”**, avant toute proposition de modification : reconstruire depuis les fichiers/tests/artefacts la matrice réelle des relations `N × N`, déterminer pour chaque paire `A→B` et `B→A` si elle est **connue, autorisée, joignable, connectée et effectivement testée**, puis comparer cette matrice au graphe complet théorique.

Cela permettra de savoir avec des mesures, et non avec les rapports seuls, **quelle topologie ARTCB possède réellement aujourd'hui**.

[1]: https://github.com/thangphan205/tacacs-ng-ui/blob/main/CLAUDE.md?utm_source=chatgpt.com "tacacs-ng-ui/CLAUDE.md at main · thangphan205/tacacs-ng-ui · GitHub"
