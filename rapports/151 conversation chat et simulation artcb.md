Oui. **J’intègre maintenant explicitement le cas où A possède déjà une première machine, puis veut exploiter une deuxième machine et doit obligatoirement l’associer à B**, tout en conservant la **quantité dynamique déterminée par la capacité réelle du réseau**.

Et je corrige un point de ma simulation précédente : **B ne doit pas être traité uniquement comme un Finder/HBP**. Dans ton modèle, B est aussi **l’humain associé à la deuxième machine**. Il peut donc avoir un droit économique lié à cette machine, distinct de sa contribution HBP éventuelle.

Les fichiers confirment trois principes : le nombre de pré-blocs doit être déterminé dynamiquement par la charge/capacité, les pré-blocs ne créent pas de récompenses supplémentaires, et le paiement d'un humain associé doit être effectué directement par le protocole.  

## Expertises mobilisées

* **Architecture blockchain / consensus PoL**
* **Partitionnement dynamique et allocation de capacité**
* **Tokenomics**
* **Mechanism design**
* **Anti-Sybil / identité humaine**
* **Identité matérielle TPM**
* **Économie des incitations A/B**
* **Comptabilité de récompense et règlement on-chain**

---

# 1. Le scénario exact

On part de :

```text
HUMAIN A
│
├── Wallet A
│
├── Machine A1
│
└── Machine A2
          │
          │ obligation
          ▼
       HUMAIN B
       │
       └── Wallet B
```

### Machine A1

A peut l'exploiter directement :

$$
A + M_1
$$

Pas besoin de B.

### Machine A2

A reste propriétaire de la machine :

$$
Owner(M_2)=A
$$

mais le protocole exige :

$$
Human(M_2)=B
$$

avec :

$$
B\neq A
$$

et B doit être un **humain vérifié indépendamment**.

C'est cohérent avec le mécanisme déjà défini : une capacité matérielle supplémentaire ne doit pas permettre à A de multiplier simplement son pouvoir économique sans introduire un nouvel humain vérifié. 

---

# 2. A et B ont donc des droits différents

C'est fondamental.

| Élément                                         |       A |        B |
| ----------------------------------------------- | ------: | -------: |
| Possède M2                                      |     Oui |      Non |
| Identité humaine                                |     Oui |      Oui |
| Wallet propre                                   |     Oui |      Oui |
| Identité matérielle M2                          |       — | associée |
| Peut recevoir Reward M2                         |     Oui |      Oui |
| Contrôle le wallet de l'autre                   | **Non** |  **Non** |
| Peut retirer unilatéralement la part de l'autre | **Non** |  **Non** |
| Peut quitter l'association                      |       — |  **Oui** |

Le protocole doit donc enregistrer quelque chose comme :

```text
Machine M2
│
├── Owner = A
├── HumanBinding = B
├── WalletOwner = B
└── RewardPolicy = dynamique
```

---

# 3. Et maintenant la quantité dynamique

C'est ici que ta dernière correction est importante.

On **ne fixe pas** :

```text
M2 = X PoL
M2 = Y TX
M2 = Z HBP
```

à l'avance.

Le protocole mesure la capacité réelle du réseau **avant chaque bloc**.

Conceptuellement :

$$
C_{block}
=
\min(
C_{compute},
C_{memory},
C_{network},
C_{validation},
C_{consensus}
)
$$

puis applique une marge de sécurité :

$$
C_{target}
=
\eta C_{block}
$$

avec par exemple :

$$
\eta \in [0.70,0.80]
$$

selon les paramètres déjà étudiés.

Donc la quantité de travail admissible est recalculée :

```text
État réseau précédent
        │
        ▼
mesure capacité réelle
        │
        ▼
capacité cible
        │
        ▼
quantité TX / PoL / HBP
        │
        ▼
création des PB nécessaires
        │
        ▼
bloc
```

**Le nombre de PB n'est donc jamais une constante.**

---

# 4. Exemple concret : A ajoute M2

Prenons un état réseau donné.

Le scheduler détermine pour le prochain bloc :

```text
Capacité cible du bloc :

TX  = 1 200
PoL = 8 000 WorkUnits
HBP = 400 ProofUnits
```

Ce sont des **capacités calculées pour cette fenêtre**, pas des récompenses.

Supposons :

```text
M1 = capacité disponible 3 000 WorkUnits
M2 = capacité disponible 5 000 WorkUnits
```

Alors :

$$
3\,000+5\,000=8\,000
$$

La capacité PoL du bloc est exactement saturée.

---

# 5. Le protocole ne donne pas 50 ARTCB à chaque machine

On conserve :

$$
\boxed{R_{Block}=50\ ARTCB}
$$

et :

$$
\boxed{
\sum Reward(PB_i)\le50
}
$$

Les pré-blocs servent uniquement à répartir le travail.

Par exemple :

```text
8 000 WorkUnits
       │
       ▼
Partition dynamique
       │
 ┌─────┼─────┬─────┐
 ▼     ▼     ▼     ▼
PB1   PB2   PB3   PB4
```

Si la capacité change au bloc suivant :

```text
11 600 WorkUnits
       │
       ▼
PB1 ... PB6
```

Le nombre de PB passe de 4 à 6 **sans passer de 50 à 300 ARTCB**.

C'est exactement la séparation entre quantité de travail, nombre de pré-blocs et budget du bloc confirmée par les simulations. 

---

# 6. Maintenant faisons réellement travailler A et B

On prend trois utilisateurs :

### A

```text
Human A
Wallet A

Machine A1
Machine A2
```

### B

```text
Human B
Wallet B
```

### C

```text
Human C
Wallet C
Machine C1
```

Le réseau dispose donc de :

```text
M1 = A1 → A
M2 = A2 → B
M3 = C1 → C
```

---

# 7. Les Jobs arrivent

Supposons que le Work Pool contienne :

| Job  | Provider | Travail demandé | Machine exécutante |
| ---- | -------- | --------------: | ------------------ |
| J001 | A        |           1 200 | A1                 |
| J002 | A        |           1 000 | A2                 |
| J003 | B        |             800 | A2                 |
| J004 | C        |           1 500 | C1                 |
| J005 | B        |             900 | A2                 |
| J006 | C        |           1 600 | C1                 |

Total :

$$
1\,200+1\,000+800+1\,500+900+1\,600
=
\boxed{7\,000}
$$

WorkUnits.

Le scheduler avait déterminé :

$$
C_{PoL,target}=8\,000
$$

Donc les 7 000 unités sont admissibles.

---

# 8. Maintenant apparaît une distinction cruciale

Pour **J002**, par exemple :

```text
Provider = A
Machine = A2
Human binding = B
Worker = A2
```

Il y a potentiellement **trois dimensions économiques** :

### A

fournit le Job.

### A2

fournit la puissance matérielle.

### B

fournit l'identité humaine obligatoire attachée à A2.

Il ne faut surtout pas écraser ces trois dimensions dans un seul champ `owner`.

---

# 9. Le registre du Job doit donc contenir

```text
J002
│
├── JobProvider
│     └── Human A
│
├── Machine
│     └── A2
│
├── MachineOwner
│     └── A
│
├── HumanBinding
│     └── B
│
├── Worker
│     └── A2
│
├── PoLWeight
│
└── ValidationProof
```

C'est beaucoup plus précis que :

```text
Job → A
```

---

# 10. Maintenant calculons le reward

Prenons, pour **cette simulation uniquement**, le partage initial déjà utilisé dans les simulations :

$$
50\ ARTCB
$$

avec :

$$
50\%\rightarrow Worker/PoL
$$

et :

$$
50\%\rightarrow HBP/Human
$$

donc :

$$
25+25=50.
$$

Cette séparation est documentée comme redistribution du reward existant, pas comme émission supplémentaire. 

---

# 11. Pool Worker

$$
R_W=25
$$

Les contributions machines :

| Machine   |                   Travail |
| --------- | ------------------------: |
| A1        |                     1 200 |
| A2        | 1 000 + 800 + 900 = 2 700 |
| C1        |     1 500 + 1 600 = 3 100 |
| **Total** |                 **7 000** |

Donc :

### A1

$$
25\times\frac{1\,200}{7\,000}
=
\boxed{4,285714}
$$

### A2

$$
25\times\frac{2\,700}{7\,000}
=
\boxed{9,642857}
$$

### C1

$$
25\times\frac{3\,100}{7\,000}
=
\boxed{11,071429}
$$

Vérification :

$$
4,285714+9,642857+11,071429
=
\boxed{25}
$$

---

# 12. Mais A2 doit maintenant être séparée entre A et B

C'est **là** que ta règle A/B intervient.

A2 appartient à A, mais est liée à B.

Pour la deuxième machine, la règle de départ est :

$$
P_A=50\%
$$

$$
P_B=50\%
$$

Donc les 9,642857 ARTCB générés par A2 sont répartis :

### A

$$
9,642857\times50\%
=
\boxed{4,821429}
$$

### B

$$
9,642857\times50\%
=
\boxed{4,821429}
$$

---

# 13. Mais attention : B ne reçoit pas uniquement cela

B peut également être **Job Provider**.

Dans notre exemple :

```text
J003 → Provider B
J005 → Provider B
```

Donc B a aussi produit une contribution cognitive initiale.

Il faut donc distinguer :

$$
Reward_{machine}
$$

de :

$$
Reward_{provider}
$$

et éventuellement :

$$
Reward_{HBP}
$$

C'est précisément la séparation que nous avions identifiée dans le fichier consacré au Job Provider : le Provider apporte la matière première du Job et ne doit pas être confondu avec le Worker. 

---

# 14. Le paiement de B devient donc potentiellement trois fois traçable

Pour B :

```text
B
│
├── ① Human binding M2
│      └── Reward associé à M2
│
├── ② Job Provider
│      └── Reward Provider
│
└── ③ HBP
       └── Reward HBP
```

Et ces trois montants doivent être comptabilisés séparément.

### On ne doit pas écrire :

```text
B = 8,7 ARTCB
```

sans expliquer pourquoi.

On doit écrire :

```text
B
├── Machine-binding reward = X
├── Job Provider reward    = Y
└── HBP reward             = Z
                         ─────
                           Total
```

---

# 15. Exemple de règlement complet

Je vais prendre un paramètre expérimental pour le Provider afin de ne pas le présenter comme déjà verrouillé :

$$
30\%\ Provider
$$

et :

$$
70\%\ Worker
$$

sur le **pool PoL**, comme dans la simulation précédente.

Donc :

$$
25\ ARTCB
$$

devient :

$$
7,5\ Provider
$$

et :

$$
17,5\ Worker
$$

### Worker pool

A1 :

$$
17,5\times\frac{1200}{7000}
=
\boxed{3,000000}
$$

A2 :

$$
17,5\times\frac{2700}{7000}
=
\boxed{6,750000}
$$

C1 :

$$
17,5\times\frac{3100}{7000}
=
\boxed{7,750000}
$$

Total :

$$
17,5
$$

---

# 16. A/B sur A2

A2 produit :

$$
6,75\ ARTCB
$$

de Worker reward.

Avec :

$$
50/50
$$

on obtient :

| Bénéficiaire |   Part A2 |
| ------------ | --------: |
| A            | **3,375** |
| B            | **3,375** |
| **Total**    | **6,750** |

---

# 17. Provider Pool

Les Providers sont :

### A

J001 + J002 :

$$
1200+1000=2200
$$

### B

J003 + J005 :

$$
800+900=1700
$$

### C

J004 + J006 :

$$
1500+1600=3100
$$

Total :

$$
7000
$$

Pool Provider :

$$
7,5
$$

Donc :

### A

$$
7,5\times\frac{2200}{7000}
=
\boxed{2,357143}
$$

### B

$$
7,5\times\frac{1700}{7000}
=
\boxed{1,821429}
$$

### C

$$
7,5\times\frac{3100}{7000}
=
\boxed{3,321429}
$$

Total :

$$
\boxed{7,5}
$$

---

# 18. HBP

Le HBP constitue l'autre partie du budget.

$$
\boxed{25\ ARTCB}
$$

Supposons que trois humains aient des contributions HBP vérifiées :

| Human     | HBP Weight |
| --------- | ---------: |
| B         |        100 |
| C         |         50 |
| D         |         25 |
| **Total** |    **175** |

Alors :

### B

$$
25\times\frac{100}{175}
=
\boxed{14,285714}
$$

### C

$$
25\times\frac{50}{175}
=
\boxed{7,142857}
$$

### D

$$
25\times\frac{25}{175}
=
\boxed{3,571429}
$$

Total :

$$
25
$$

---

# 19. Règlement final de chaque humain

Maintenant nous pouvons enfin répondre à ta demande : **qui reçoit exactement quoi ?**

### A

A reçoit :

* Provider : **2,357143**
* Worker sur A1 : **3,000000**
* Worker sur A2 : **3,375000**

Donc :

$$
\boxed{A=8,732143\ ARTCB}
$$

---

### B

B reçoit :

* Worker-binding A2 : **3,375000**
* Provider : **1,821429**
* HBP : **14,285714**

Donc :

$$
\boxed{B=19,482143\ ARTCB}
$$

---

### C

C reçoit :

* Worker C1 : **7,750000**
* Provider : **3,321429**
* HBP : **7,142857**

Donc :

$$
\boxed{C=18,214286\ ARTCB}
$$

---

### D

D reçoit :

$$
\boxed{3,571429}
$$

---

# 20. Vérification comptable totale

Addition :

$$
8,732143
+
19,482143
+
18,214286
+
3,571429
$$

=

$$
\boxed{50,000001}
$$

L'écart de \(0,000001\) vient uniquement de l'arrondi décimal.

En arithmétique exacte :

$$
\boxed{50\ ARTCB}
$$

Pas :

* 55 ;
* 75 ;
* 100 ;
* ou 50 par pré-bloc.

**Exactement 50.**

---

# 21. Et maintenant la partie la plus importante : le nombre de PB

Supposons que la capacité réelle mesurée avant ce bloc soit :

$$
C_{PoL,target}=8\,000
$$

et que nous ayons :

$$
Work=7\,000.
$$

Avec une capacité dynamique de :

$$
C_{PB}=2\,000
$$

le protocole crée :

$$
N_{PB}
=
\left\lceil\frac{7\,000}{2\,000}\right\rceil
=
\boxed{4}
$$

pré-blocs.

```text
7 000 WorkUnits
       │
       ▼
Partition dynamique
       │
 ┌─────┼─────┬─────┐
 ▼     ▼     ▼     ▼
PB1   PB2   PB3   PB4
1750  1750  1750  1750
       │
       ▼
  validation globale
       │
       ▼
 50 ARTCB
```

---

# 22. Si le réseau s'améliore au bloc suivant

Supposons que le système mesure :

$$
C_{PB}=3\,000
$$

et que la demande soit :

$$
11\,000
$$

Alors :

$$
N_{PB}
=
\left\lceil
\frac{11\,000}{3\,000}
\right\rceil
=
\boxed{4}
$$

Le bloc suivant peut donc traiter beaucoup plus de travail **avec le même principe de budget**.

Si la capacité chute :

$$
C_{PB}=1\,000
$$

alors :

$$
N_{PB}
=
\left\lceil
\frac{11\,000}{1\,000}
\right\rceil
=
\boxed{11}
$$

Le protocole augmente automatiquement le nombre de PB.

---

# 23. Donc A ne « gagne » pas simplement parce qu'il possède deux machines

C'est une distinction essentielle.

A possède :

```text
M1
M2
```

mais :

```text
M1 → A
M2 → A + B
```

Le protocole regarde ensuite **le travail réellement validé**, pas simplement le nombre de machines.

Ainsi :

$$
Reward(M_2)
\propto
WorkValidated(M_2)
$$

et non :

$$
Reward(M_2)=Reward(M_1)
$$

automatiquement.

---

# 24. Et la règle A/B doit elle-même devenir dynamique

Tu avais déjà validé le principe :

$$
50\%\rightarrow10\%
$$

pour la concentration du propriétaire lorsqu'il contrôle plusieurs machines. 

Je l'appliquerais **par machine supplémentaire**, pas à l'ensemble du portefeuille d'A.

Exemple :

| Machine | Owner | Human binding | Part Owner | Part Human |
| ------- | ----- | ------------- | ---------: | ---------: |
| M1      | A     | A             |      100 % |        0 % |
| M2      | A     | B             |   **50 %** |   **50 %** |
| M3      | A     | C             |   **40 %** |   **60 %** |
| M4      | A     | D             |   **30 %** |   **70 %** |
| M5      | A     | E             |   **20 %** |   **80 %** |
| M6+     | A     | F…            |   **10 %** |   **90 %** |

Cela évite que la deuxième machine et la centième machine aient exactement la même structure d'incitation.

---

# 25. Mais attention : je ne fusionnerais PAS A/B avec HBP

C'est probablement la correction la plus importante de la simulation.

Il existe maintenant **trois mécanismes distincts** :

### 1. Worker / machine

$$
Machine\rightarrow PoL
$$

### 2. Job Provider

$$
AI\ Result\rightarrow Job\rightarrow ProviderReward
$$

### 3. Human Binding / HBP

$$
Human\rightarrow HBP
$$

Et, pour une deuxième machine :

$$
Machine_A+B
\rightarrow
BindingReward
$$

Ces quatre flux peuvent concerner la même personne, mais **ils ne doivent pas être mélangés dans le ledger**.

---

# 26. Le ledger final doit donc être détaillé

Pour B, par exemple :

```text
SETTLEMENT #N

Wallet B
│
├── SOURCE: MACHINE_BINDING
│      Machine = A2
│      Amount = 3.375 ARTCB
│
├── SOURCE: JOB_PROVIDER
│      Jobs = J003,J005
│      Amount = 1.821429 ARTCB
│
└── SOURCE: HBP
       Weight = 100
       Amount = 14.285714 ARTCB

TOTAL
= 19.482143 ARTCB
```

Cela permet de répondre ultérieurement à :

> **Pourquoi B a-t-il reçu 19,482143 ARTCB ?**

Sans ambiguïté.

---

# 27. Le bloc final devient donc

```text
BLOCK #N
│
├── TX
│   ├── TX001
│   ├── TX002
│   └── ...
│
├── DYNAMIC CAPACITY
│   ├── C_TX
│   ├── C_PoL
│   ├── C_HBP
│   └── C_validation
│
├── WORK POOL
│
├── PARTITION MAP
│   ├── PB01
│   ├── PB02
│   ├── PB03
│   └── PB04
│
├── GLOBAL VALIDATION
│
└── SETTLEMENT
    │
    ├── Provider Pool
    ├── Worker Pool
    ├── Machine Binding
    └── HBP Pool
```

Et surtout :

$$
\boxed{
Reward_{Block}
=
Reward_{Provider}
+
Reward_{Worker}
+
Reward_{Binding}
+
Reward_{HBP}
}
$$

**sans émission supplémentaire liée aux PB.**

---

## 28. La règle que je considère maintenant comme la plus propre

Pour éviter toute confusion dans les prochaines simulations, je propose de verrouiller conceptuellement cette comptabilité :

$$
\boxed{
R_{Block}=R_{TX\text{-}related}+R_{PoL}+R_{HBP}
}
$$

et, à l'intérieur du PoL :

$$
\boxed{
R_{PoL}
=
R_{Provider}
+
R_{Machine/Worker}
}
$$

tandis que pour chaque machine multi-humaine :

$$
\boxed{
R_{Machine}
=
R_{Owner}
+
R_{BoundHuman}
}
$$

**Mais il faut éviter de compter deux fois la même enveloppe.** La part A/B de la machine doit donc être une **partition du Worker reward de cette machine**, pas une nouvelle récompense.

C'est cette dernière précision qui rend le modèle cohérent.

### En résumé

Pour **A + deuxième machine + B** :

```text
A possède M2
       │
       ▼
M2 doit être lié à B
       │
       ▼
M2 produit réellement du PoL
       │
       ▼
récompense M2 calculée selon son travail validé
       │
       ├── A : part propriétaire
       └── B : part humain lié
```

Puis, indépendamment :

```text
A ── Job Provider ──► Provider Reward
B ── Job Provider ──► Provider Reward
B ── HBP ───────────► HBP Reward
```

et **le nombre de pré-blocs est recalculé avant chaque bloc en fonction de la capacité réelle du réseau**, sans changer le budget monétaire du bloc. 

C'est cette architecture que j'utiliserais pour la prochaine simulation multi-utilisateurs : **A1, A2+B, C1, D1…, plusieurs Jobs, plusieurs TX, capacité dynamique avant/après chaque bloc, PB dynamiques, Provider, Worker, Binding A/B et HBP, avec le règlement de chaque wallet de bout en bout.**
