Oui. Et après avoir recroisé la simulation avec les fichiers ARTCB, je pense que **la confusion vient d'un point précis : tu identifies deux acteurs différents, mais nous les avons parfois mis dans le même “pool de récompense”.**

Tu identifies bien :

1. **le mineur/Worker PoL** → celui qui exécute le Job ;
2. **l'émetteur du Job / Job Provider** → celui qui apporte ou demande le travail à effectuer.

Et **ce ne sont pas nécessairement la même personne**.

Les fichiers établissent déjà trois marchés distincts : calcul/PoL, identité humaine/HBP et utilisation de la blockchain/TX. 

## 1. Le point que je corrige

Le modèle précédent :

$$
50\ ARTCB
\rightarrow
25\ Miner
+
25\ HBP
$$

répond à la question **« comment distribuer l'émission PoL ? »**

Mais il ne répond pas encore correctement à :

> **« Qui paie le Job envoyé au mineur ? »**

Ce sont deux mécanismes différents.

### Il faut donc avoir :

$$
\boxed{
JOB\ PAYMENT
\neq
BLOCK\ REWARD
}
$$

C'est probablement la distinction que tu cherches.

---

# 2. Qui sont les acteurs ?

Je les nommerais ainsi :

| Acteur                 | Fonction                  | Produit        |
| ---------------------- | ------------------------- | -------------- |
| **Job Provider**       | envoie/dépose le travail  | Job            |
| **Worker / Miner PoL** | exécute le travail        | résultat + PoL |
| **Validator**          | vérifie le résultat       | validation     |
| **HBP/Finder**         | apporte la preuve humaine | HBP            |
| **User**               | utilise la blockchain     | TX             |
| **Protocol**           | orchestre + distribue     | récompenses    |

Donc :

```text
JOB PROVIDER
     │
     │ Job
     ▼
 WORK POOL
     │
     ▼
 DYNAMIC PARTITIONER
     │
     ├── PB-1 ──→ Worker A
     ├── PB-2 ──→ Worker B
     ├── PB-3 ──→ Worker C
     └── PB-N ──→ Worker N
                    │
                    ▼
                 résultat
                    │
                    ▼
               VALIDATION
```

Le système sait alors exactement **quel Worker a réalisé quel morceau du Job**.

Les pré-blocs dynamiques servent précisément à empêcher les doublons : chaque `WorkID` doit être affecté une seule fois à une partition. 

---

# 3. Alors qui paie le Worker ?

Il faut distinguer **deux cas**.

## Cas A — Job payé par un client

Exemple :

> Une entreprise veut faire analyser 10 millions de documents.

Elle dépose :

$$
Job=10M\ documents
$$

et paie :

$$
JobFee=1000\ ARTCB
$$

par exemple.

Le flux devient :

```text
CLIENT / JOB PROVIDER
        │
        │ 1000 ARTCB
        ▼
   JOB ESCROW
        │
        ▼
     WORKERS
        │
        ▼
 travail vérifié
        │
        ▼
     paiement
```

Ici, **les 1000 ARTCB ne sont pas une récompense monétaire créée par le protocole**.

Ce sont des ARTCB déjà détenus par le client.

---

# 4. Le Worker reçoit alors deux choses potentiellement différentes

C'est là que ton système devient beaucoup plus clair.

Le Worker peut recevoir :

### A. Paiement du Job

$$
\boxed{JobPayment}
$$

payé par celui qui a demandé le travail.

### B. Récompense PoL

$$
\boxed{PoLReward}
$$

payée par le protocole pour avoir fourni du travail utile validé.

Donc :

$$
\boxed{
WorkerIncome
=
JobPayment
+
PoLReward
}
$$

Ce sont deux flux différents.

---

# 5. Et le Job Provider reçoit-il quelque chose ?

Pas automatiquement.

Le Job Provider est celui qui **achète/utilise la capacité de calcul**.

Il paie donc normalement :

$$
JobFee
$$

et reçoit en échange :

$$
VerifiedResult.
$$

Donc :

```text
          JOB PROVIDER
               │
          paie JobFee
               │
               ▼
          PROTOCOLE
               │
       distribue le travail
               │
               ▼
            WORKER
               │
          produit résultat
               │
               ▼
        JOB PROVIDER
```

C'est un **marché du calcul utile**.

---

# 6. Mais alors à quoi servent les TX ?

Une TX n'est pas nécessairement le paiement du Job.

Il faut distinguer :

### TX de protocole

$$
User\rightarrow TX
$$

Le User paie éventuellement :

$$
TXFee.
$$

Cette fee sert à utiliser l'infrastructure blockchain.

### Job

$$
JobProvider\rightarrow Job
$$

Le Job Provider paie :

$$
JobFee.
$$

Cette fee sert à acheter une capacité de travail.

Donc :

$$
\boxed{
TXFee\neq JobFee
}
$$

sauf si nous décidons explicitement de faire du Job lui-même une transaction.

---

# 7. Et HBP ?

HBP est encore autre chose.

Le Finder/HBP ne reçoit pas une partie du `JobFee` simplement parce qu'il existe.

Il reçoit une part du mécanisme HBP défini par le protocole.

Les simulations existantes définissent :

$$
R_{PoL}=R_{Miner}+R_{Finder}
$$

et non une nouvelle émission pour le Finder. 

Donc, si le modèle choisi est :

$$
10\%\rightarrow60\%\rightarrow20\%
$$

il faut appliquer cette fonction **au budget protocolaire PoL/HBP**, pas au prix commercial du Job.

---

# 8. Exemple concret avec TON système

Prenons un Job :

> Client A veut traiter 1 000 000 documents.

Il paie :

$$
JobFee=100\ ARTCB.
$$

Le protocole reçoit donc :

$$
100\ ARTCB
$$

en escrow.

Le travail est réparti :

```text
1 000 000 documents
        │
        ▼
Dynamic Partition
        │
 ┌──────┼──────┐
 ▼      ▼      ▼
PB1    PB2    PB3 ... PBN
 │      │      │
 W1     W2     W3 ... WN
```

Chaque Worker réalise son travail.

Supposons :

| Worker    | Travail validé | Part du Job |
| --------- | -------------: | ----------: |
| W1        |        300 000 |        30 % |
| W2        |        200 000 |        20 % |
| W3        |        100 000 |        10 % |
| W4        |        400 000 |        40 % |
| **Total** |  **1 000 000** |   **100 %** |

Alors :

$$
100\times30\%=30
$$

$$
100\times20\%=20
$$

etc.

Donc :

$$
\boxed{
W1=30,\ W2=20,\ W3=10,\ W4=40
}
$$

Le Job est payé par le **Job Provider**.

---

# 9. Maintenant ajoutons la récompense PoL

Supposons que le bloc ait :

$$
R_{PoL}=50\ ARTCB.
$$

Et supposons provisoirement :

$$
P_{HBP}=60\%.
$$

Alors :

$$
R_{HBP}=30
$$

et :

$$
R_{Worker}=20.
$$

Le Worker peut donc avoir :

$$
JobPayment + PoLReward.
$$

Par exemple W1 :

$$
30\ JobPayment
+
6\ PoLReward
=
36\ ARTCB.
$$

Mais attention :

**les 30 ARTCB du Job et les 6 ARTCB de PoL n'ont pas la même origine.**

---

# 10. Le flux complet devient enfin compréhensible

```text
                         CLIENT
                    / JOB PROVIDER
                         │
                         │ JobFee
                         ▼
                  ┌──────────────┐
                  │ JOB ESCROW   │
                  └──────┬───────┘
                         │
                         ▼
                    WORK POOL
                         │
                         ▼
                DYNAMIC PARTITION
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
             PB1        PB2        PBN
              │          │          │
             W1         W2         WN
              │          │          │
              └──────────┼──────────┘
                         ▼
                    VALIDATION
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        JOB PAYMENT             PoL PROOF
              │                     │
              │                     ▼
              │                50 ARTCB
              │                     │
              │             ┌───────┴───────┐
              │             ▼               ▼
              │          Worker Pool      HBP Pool
              │             │               │
              ▼             ▼               ▼
          Workers       PoL Workers       Finders
```

---

# 11. Maintenant le fameux 10 → 60 → 20 %

C'est **ici** qu'il faut être extrêmement précis.

D'après le fichier de simulation, le modèle `10 % → 60 % → 20 %` était présenté comme une **part HBP de la récompense PoL**, avec un pic à 60 % pendant la phase d'expansion humaine. 

Donc :

$$
P_H(t)=10\%\rightarrow60\%\rightarrow20\%.
$$

Et :

$$
\boxed{
R_{HBP}=P_H(t)\times R_{PoL}
}
$$

$$
\boxed{
R_{PoLWorker}=(1-P_H(t))\times R_{PoL}
}
$$

**Ce mécanisme ne dit pas encore comment partager le JobFee.**

C'est une couche différente.

---

# 12. Donc voici la séparation que je recommande

## Couche 1 — TX

$$
\boxed{TXFee}
$$

Paiement pour **utiliser la blockchain**.

---

## Couche 2 — Job

$$
\boxed{JobFee}
$$

Paiement du **travail demandé par un client**.

---

## Couche 3 — PoL

$$
\boxed{PoLReward}
$$

Récompense du **travail utile validé**.

---

## Couche 4 — HBP

$$
\boxed{HBPReward=P_H\times PoLReward}
$$

Récompense du mécanisme d'identité humaine.

---

# 13. Et cela répond à ta question initiale

Tu dis :

> « J'identifie le mineur PoL et celui qui envoie le Job. »

**Oui. Il faut absolument les identifier séparément.**

Le protocole devrait donc avoir au minimum :

$$
\boxed{
JobProviderID
}
$$

$$
\boxed{
WorkerID
}
$$

$$
\boxed{
WorkID
}
$$

$$
\boxed{
PreBlockID
}
$$

$$
\boxed{
ValidatorID
}
$$

et, lorsque nécessaire :

$$
\boxed{
HumanID/HBPID
}
$$

---

# 14. Le paiement doit être calculé à partir de ces relations

Par exemple :

$$
Job(J)
\rightarrow
Provider(P)
$$

puis :

$$
WorkItem_i
\rightarrow
Worker(W_i)
$$

puis :

$$
WorkItem_i
\rightarrow
PreBlock(PB_j)
$$

puis :

$$
PB_j
\rightarrow
Block(B)
$$

et finalement :

$$
Block(B)
\rightarrow
RewardDistribution.
$$

Ainsi on peut produire un relevé parfaitement traçable :

| Élément    | Payeur                      | Bénéficiaire                      | Motif                |
| ---------- | --------------------------- | --------------------------------- | -------------------- |
| TX fee     | User                        | protocole/validateurs selon règle | transaction          |
| Job fee    | Job Provider                | Workers                           | travail commandé     |
| PoL reward | protocole                   | Worker                            | travail utile validé |
| HBP reward | protocole                   | Finder/Human pool                 | HBP                  |
| Pré-bloc   | **aucun paiement autonome** | —                                 | partition technique  |

---

# 15. Et je corrige un point de la simulation précédente

Le `50 ARTCB` que nous utilisions était présenté comme :

$$
R_{PoL}=50.
$$

Il ne faut donc **pas** écrire :

> « le client paie 50 ARTCB au mineur ».

Ce serait faux.

Il faut écrire :

> **Le protocole attribue 50 ARTCB de récompense PoL au bloc, puis cette enveloppe est répartie selon les règles Worker/HBP.**

Le Job Provider peut, en parallèle, payer un `JobFee`.

Les fichiers eux-mêmes insistent sur cette séparation entre **récompense protocolaire** et **revenu économique réel**. 

---

# 16. Le modèle économique que je considère maintenant le plus propre

$$
\boxed{
\underbrace{TXFee}_{utilisation}
+
\underbrace{JobFee}_{travail\ acheté}
+
\underbrace{PoLReward}_{incitation\ protocolaire}
+
\underbrace{HBPReward}_{identité\ humaine}
}
$$

Mais attention :

**TXFee et JobFee ne doivent pas être inventés comme s'ils étaient déjà spécifiés dans le protocole.** Les fichiers confirment les trois marchés et le principe de récompense, mais la formule définitive de `JobFee` reste à spécifier. 

---

## Et oui : ton intuition sur le « 10 → 60 → 20 » est bien celle à conserver

Mais **10 → 60 → 20 ne doit pas être présenté comme le paiement du Job**.

Il représente la **part du budget PoL réservée au mécanisme humain/HBP**.

Donc, conceptuellement :

$$
\boxed{
JobProvider
\xrightarrow{JobFee}
Worker
}
$$

pendant que :

$$
\boxed{
Protocol
\xrightarrow{PoLReward}
Worker+HBP
}
$$

et :

$$
\boxed{
User
\xrightarrow{TXFee}
Blockchain
}
$$

C'est cette séparation qui permet enfin de répondre sans ambiguïté à **« qui paie qui, pour quoi ? »**.

