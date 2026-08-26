Exactement. **Tu ne proposes pas “3 pré-blocs par dimension”.** J'avais introduit cette limite à tort.

Ton idée est plus précise :

> **Le protocole crée dynamiquement et uniquement le nombre de pré-blocs nécessaire pour répartir le travail disponible, sans créer plusieurs pré-blocs concurrents contenant potentiellement les mêmes éléments.**

Et cela change fortement l'architecture.

## 1. Le principe corrigé

Il ne faut pas faire :

```text
PoL
 ├── PB1
 ├── PB2
 └── PB3
```

puis demander :

> lequel des trois est le bon ?

Cela créerait exactement le problème que tu viens d'identifier : **concurrence, doublons, sélection inutile**.

Il faut plutôt faire :

```text
                    POOL PoL
                       │
                       ▼
                PLANIFICATEUR
                       │
          détermine la capacité nécessaire
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       PB-PoL-1     PB-PoL-2     PB-PoL-3
          │            │            │
       travail A     travail B     travail C
```

Mais surtout :

$$
\boxed{WorkID(A)\neq WorkID(B)\neq WorkID(C)}
$$

**dès la création.**

Les pré-blocs sont donc **partitionnés**, et non concurrents.

---

# 2. La bonne architecture : partition dynamique

Je proposerais maintenant ce modèle :

$$
\boxed{
Pool_d
\rightarrow
Partitionneur_d
\rightarrow
N_d\ PreBlocks
}
$$

où :

$$
N_d=
\left\lceil
\frac{Demand_d}{Capacity_{PB,d}}
\right\rceil
$$

Mais cette formule n'est qu'un mécanisme de dimensionnement.

Le point essentiel est :

$$
\boxed{
1\ élément\ de\ travail
\rightarrow
1\ seul\ PreBlock
}
$$

pour une fenêtre donnée.

---

# 3. Exemple simple

Supposons :

### TX disponibles

$$
25\,000
$$

### capacité optimale d'un pré-bloc

$$
5\,000
$$

Le protocole crée :

$$
N_{TX}=
\lceil25\,000/5\,000\rceil
=5
$$

Donc :

```text
TX PREBLOCKS

PB-TX-01 → TX 1–5 000
PB-TX-02 → TX 5 001–10 000
PB-TX-03 → TX 10 001–15 000
PB-TX-04 → TX 15 001–20 000
PB-TX-05 → TX 20 001–25 000
```

**Pas de PB6, PB7, PB8 inutiles.**

Et surtout :

```text
TX 7342
   │
   └──────► PB-TX-02
```

Il n'existe pas simultanément dans PB-TX-01 ou PB-TX-03.

---

# 4. Mais il faut aller encore plus loin

Je ne partitionnerais pas seulement selon une position :

> TX 1–5000, TX 5001–10000...

Car l'ordre d'arrivée peut changer.

Il faut une **identité déterministe d'affectation**.

Par exemple :

$$
PartitionID=
Hash(
WorkID,\ Epoch,\ ParentStateRoot
)
\bmod N
$$

Donc :

```text
WorkID 001
   ↓
hash
   ↓
PB-07

WorkID 002
   ↓
hash
   ↓
PB-03

WorkID 003
   ↓
hash
   ↓
PB-11
```

Ainsi plusieurs producteurs peuvent travailler en parallèle **sans choisir arbitrairement le même travail**.

---

# 5. Mais attention à un problème

Si :

$$
N=10
$$

et qu'on augmente ensuite à :

$$
N=20
$$

le hash modulo change.

Certains travaux pourraient changer de pré-bloc.

Donc il faut éviter une répartition instable.

Je recommande plutôt un **rendezvous hashing / consistent assignment** ou une table de partition déterministe associée à l'époque.

Le principe :

$$
\boxed{
Epoch + ParentStateRoot
\rightarrow PartitionMap
}
$$

Cette carte reste fixe pendant la fenêtre de construction.

---

# 6. Donc chaque bloc possède une "carte de pré-blocs"

Par exemple :

```text
BLOCK N
│
├── ParentStateRoot
│
├── PartitionMap TX
│     ├── PB-TX-01
│     ├── PB-TX-02
│     └── ...
│
├── PartitionMap PoL
│     ├── PB-PoL-01
│     ├── PB-PoL-02
│     └── ...
│
└── PartitionMap HBP
      ├── PB-HBP-01
      ├── PB-HBP-02
      └── ...
```

Et cette carte est déterminée **avant que le travail soit réparti**.

---

# 7. Le point essentiel : pas de "candidat concurrent"

Je corrige donc également ma proposition précédente.

Nous ne voulons PAS :

```text
             mêmes données
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
       C1       C2       C3
        │        │        │
        └────────┼────────┘
                 ▼
              choisir
```

Parce que cela crée :

* travail dupliqué ;
* validation répétée ;
* compétition ;
* consommation CPU inutile ;
* possibilité de double paiement ;
* problème de choix entre candidats.

Ton architecture doit plutôt être :

```text
                 WORK
                  │
             PARTITION
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
     PB-A       PB-B       PB-C
       │          │          │
       │          │          │
       └──────────┼──────────┘
                  ▼
              ASSEMBLY
                  │
                  ▼
             FINAL BLOCK
```

Les pré-blocs sont **complémentaires**, pas concurrents.

---

# 8. Et le nombre de pré-blocs doit être automatique

C'est là que ta correction est importante.

Le protocole doit calculer :

$$
N_{TX}
$$

$$
N_{PoL}
$$

$$
N_{HBP}
$$

indépendamment.

Par exemple :

| Dimension | Travail disponible | Capacité PB | PB nécessaires |
| --------- | -----------------: | ----------: | -------------: |
| TX        |            100 000 |       5 000 |         **20** |
| PoL       |             37 000 |       4 000 |         **10** |
| HBP       |              8 000 |       2 000 |          **4** |

Le bloc peut donc avoir :

$$
\boxed{
20\ TX\ PB+
10\ PoL\ PB+
4\ HBP\ PB
}
$$

soit :

$$
\boxed{34\ pré-blocs}
$$

et non 9.

---

# 9. Et si demain il y a 1 milliard d'utilisateurs ?

Le protocole ne doit pas avoir une constante :

$$
N=3.
$$

Il calcule :

$$
N=f(Demand,Capacity,ResourceLimit).
$$

Donc il peut avoir :

```text
Petite échelle
TX   → 2 PB
PoL  → 1 PB
HBP  → 1 PB
```

puis :

```text
Grande échelle
TX   → 12 000 PB
PoL  → 8 000 PB
HBP  → 2 000 PB
```

si les ressources réseau et de validation le permettent.

---

# 10. Mais il y a une limite importante

**"Autant de pré-blocs que nécessaire" ne doit pas signifier "nombre illimité de pré-blocs".**

Sinon une attaque pourrait créer :

$$
10^9
$$

petits pré-blocs contenant chacun une seule opération.

On remplacerait le problème :

> blocage par dimension

par :

> explosion du nombre de métadonnées.

Donc il faut :

$$
N_d\le N_{max,d}
$$

par fenêtre physique.

Mais le système peut ensuite créer une **nouvelle vague de partitions**.

Par exemple :

```text
Vague 1
PB1 ... PB1000
       ↓
assemblage

Vague 2
PB1001 ... PB2000
       ↓
assemblage
```

Cela conserve le parallélisme sans créer un nombre impossible de structures simultanées.

---

# 11. Encore plus important : ne pas confondre "pré-bloc" et "batch"

Je pense qu'il faut définir précisément les deux.

### Pré-bloc

Une unité de travail **engagée cryptographiquement** dans le futur bloc.

### Batch

Une simple subdivision technique pour traitement.

Un pré-bloc doit avoir une identité :

$$
PreBlockID
$$

et un engagement :

$$
PreBlockRoot.
$$

Un batch interne peut ne pas avoir cette responsabilité.

Cela évite de surcharger la blockchain de milliers de petites structures.

---

# 12. Structure que je recommande

```text
                    BLOCK N
                       │
                ParentStateRoot
                       │
                Partition Planner
                       │
       ┌───────────────┼────────────────┐
       │               │                │
       ▼               ▼                ▼
   TX Planner      PoL Planner       HBP Planner
       │               │                │
       ▼               ▼                ▼
  N_TX PBs         N_PoL PBs         N_HBP PBs
       │               │                │
       │               │                │
       └───────────────┼────────────────┘
                       ▼
                 PRE-BLOCK ROOTS
                       │
                       ▼
                 BLOCK ASSEMBLER
                       │
                       ▼
                GLOBAL VALIDATION
                       │
                       ▼
                   CONSENSUS
                       │
                       ▼
                  BLOCK N+1
```

---

# 13. Comment empêcher absolument les doublons ?

Il faut plusieurs protections.

### Niveau 1 — WorkID

Chaque travail possède :

$$
WorkID
$$

unique.

### Niveau 2 — Assignment

$$
WorkID\rightarrow PartitionID
$$

déterministe.

### Niveau 3 — Nullifier / spent marker

Une fois utilisé :

$$
Used(WorkID)=1.
$$

### Niveau 4 — Global validation

Le bloc final vérifie :

$$
\forall i,j,\quad WorkID_i\neq WorkID_j.
$$

### Niveau 5 — État parent

Tous les pré-blocs doivent être construits sur :

$$
ParentStateRoot_N.
$$

---

# 14. Le résultat est très différent de l'architecture précédente

Avant :

> « Je fabrique plusieurs candidats et je choisis le meilleur. »

Maintenant :

> **« Je divise le travail unique en partitions uniques, puis je réunis les partitions complémentaires. »**

C'est beaucoup plus propre.

Mathématiquement :

$$
W=W_1\cup W_2\cup...\cup W_N
$$

avec :

$$
W_i\cap W_j=\varnothing
\quad\text{pour}\quad i\neq j.
$$

Et :

$$
\bigcup_{i=1}^{N}W_i=W.
$$

C'est exactement la propriété que tu cherches.

---

# 15. Et cette propriété peut être étendue aux trois dimensions

Pour TX :

$$
TX=\bigsqcup_i TX_i
$$

Pour PoL :

$$
PoL=\bigsqcup_j PoL_j
$$

Pour HBP :

$$
HBP=\bigsqcup_k HBP_k
$$

où \(\bigsqcup\) signifie **union disjointe**.

Puis :

$$
Block=
TX
\cup
PoL
\cup
HBP
\cup
FinderSettlement
$$

après validation.

---

# 16. Ton architecture devient alors un véritable système de "composition"

Je la définirais provisoirement ainsi :

## **Dynamic Disjoint Pre-Block Assembly — DDPBA**

Le principe :

$$
\boxed{
Demand
\rightarrow
Dynamic\ Partition
\rightarrow
Disjoint\ PreBlocks
\rightarrow
Assembly
\rightarrow
Global\ Validation
\rightarrow
Consensus
}
$$

Et la propriété centrale :

$$
\boxed{
No\ duplicate\ work
+
No\ competing\ preblocks
+
No\ cross\ dimension\ blocking
}
$$

---

## 17. La faille restante la plus importante

Il reste une question que nous devons traiter avant de considérer cette architecture comme réellement solide :

**qui possède le droit de créer une partition et d'affecter les travaux à cette partition ?**

Si n'importe quel nœud peut dire :

> « Je crée PB-17 et j'y mets ces travaux »

nous recréons potentiellement la concurrence.

Il faut donc que la **Partition Map soit déterministe ou consensuelle avant l'affectation** :

$$
\boxed{
ParentStateRoot
+
Epoch
+
Capacity
+
Demand
\rightarrow
PartitionMap
}
$$

Une fois cette carte verrouillée :

$$
WorkID\rightarrow PB_i
$$

et aucun autre PB ne peut légitimement réclamer ce `WorkID`.

C'est, à mon avis, **la pièce manquante essentielle** de ton concept.

Et cela nous donne une architecture beaucoup plus précise à simuler : **pas “3 PB par dimension”, mais un nombre dynamique de partitions disjointes, calculé à chaque fenêtre et distribué automatiquement, avec zéro duplication intentionnelle dès la phase de création.**
