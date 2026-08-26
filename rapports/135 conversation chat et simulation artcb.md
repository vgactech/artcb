Oui. J’ai repris la règle telle que tu viens de la préciser et je la considère désormais comme **l’hypothèse de sécurité principale à tester** :

> **Un nouvel inscrit ne devient définitivement vérifié qu’après Q validations provenant de Q Finders humains distincts déjà vérifiés.**

Et pour ton scénario principal :

$$
\boxed{Q=100}
$$

La récompense PoL peut être calculée et réservée avant cela, mais elle reste non transférable jusqu'à la validation complète. Le fichier de simulation déjà produit confirme cette séparation des états `INSCRIT → FINDER_PENDING → VERIFIED → MATURED`, avec 100 attestations distinctes et contrôles anti-collusion. 

## Expertises mobilisées

* **Consensus distribué**
* **Probabilités / théorie des files**
* **Sybil-resistance**
* **Proof of Humanity / identité décentralisée**
* **Cryptographie**
* **Biométrie et liveness detection**
* **Mechanism design / théorie des incitations**
* **Tokenomics**
* **Architecture blockchain**

---

# 1. La règle devient beaucoup plus forte que « majorité des Finders »

Il y a une différence essentielle.

### Modèle majorité

Avec Q = 100 :

> 51 Finders malveillants suffisent éventuellement à imposer un faux consensus.

### Ton modèle

Avec Q = 100 :

> **les 100 validations doivent être obtenues.**

Donc, si l'on considère qu'un faux candidat ne peut être validé honnêtement par aucun Finder honnête, l'attaquant doit obtenir :

$$
\boxed{100/100}
$$

Finders malveillants dans le comité sélectionné.

La probabilité devient alors :

$$
\boxed{P_{false}=p^Q}
$$

où :

* \(p\) = proportion de Finders malveillants ;
* \(Q\) = nombre de validations obligatoires.

C'est radicalement différent d'un quorum majoritaire.

---

# 2. Résultat de la simulation : faux consensus

J'ai testé :

$$
Q=10,25,50,100,150,200
$$

avec :

$$
p=1\%,10\%,25\%,50\%.
$$

### Probabilité qu'un comité entièrement malveillant soit sélectionné

|       Q | 1 % malveillants |     10 % |        25 % |       50 % |
| ------: | ---------------: | -------: | ----------: | ---------: |
|  **10** |          1×10⁻²⁰ |  1×10⁻¹⁰ |   9,54×10⁻⁷ |  9,77×10⁻⁴ |
|  **25** |          1×10⁻⁵⁰ |  1×10⁻²⁵ |  8,88×10⁻¹⁶ |  2,98×10⁻⁸ |
|  **50** |         1×10⁻¹⁰⁰ |  1×10⁻⁵⁰ |  7,89×10⁻³¹ | 8,88×10⁻¹⁶ |
| **100** |         1×10⁻²⁰⁰ | 1×10⁻¹⁰⁰ |  6,22×10⁻⁶¹ | 7,89×10⁻³¹ |
| **150** |         1×10⁻³⁰⁰ | 1×10⁻¹⁵⁰ |  4,91×10⁻⁹¹ | 7,01×10⁻⁴⁶ |
| **200** |               ~0 | 1×10⁻²⁰⁰ | 3,87×10⁻¹²¹ | 6,22×10⁻⁶¹ |

### Conclusion immédiate

Même avec **50 % de Finders malveillants**, le modèle strict `100/100` donne :

$$
\boxed{P_{false}\approx7,9\times10^{-31}}
$$

par comité.

C'est extrêmement faible.

---

# 3. C'est précisément pour cela que je préfère ton Q=100 au modèle majoritaire

Prenons Q=100 et 50 % de Finders malveillants.

### Si majorité suffisait

Il faudrait seulement :

$$
51/100
$$

malveillants.

La probabilité d'un faux consensus est alors d'environ :

$$
46\%
$$

### Avec ta règle

Il faut :

$$
100/100.
$$

Probabilité :

$$
\boxed{7,89\times10^{-31}}
$$

La différence est gigantesque.

**C'est un argument très fort en faveur de ton mécanisme.**

---

# 4. Mais il y a un point critique

La formule :

$$
p^Q
$$

n'est valable que si les sélections sont réellement indépendantes et que l'attaquant ne peut pas influencer le comité.

Il faut donc absolument empêcher :

```text
Attaquant
   ↓
choisit ses 100 Finders
   ↓
100/100 malveillants
```

Le protocole doit faire :

```text
Candidate
    ↓
VRF / randomness protocolaire
    ↓
sélection aléatoire
    ↓
100 Finders
    ↓
validation
```

Le candidat **ne choisit pas les Finders**.

---

# 5. Il faut aussi empêcher les doublons d'identité

La règle doit être :

$$
\boxed{
HumanID_i\neq HumanID_j
}
$$

pour tout :

$$
i\neq j.
$$

Donc :

```text
Finder A → validation #1
Finder A → validation #2
Finder A → validation #3
```

ne vaut que :

$$
\boxed{1}
$$

validation.

Le réseau compte des **HumanID distincts**, pas des signatures ou des clics.

C'est déjà la direction retenue dans tes documents HBP : une contribution n'est rémunérable que lorsqu'un `HumanID_new` est définitivement validé et n'existe pas déjà dans l'ensemble des humains vérifiés. 

---

# 6. Le bootstrap que tu viens de préciser

Tu as également donné une règle importante :

> même le premier utilisateur doit attendre.

Donc je ne créerais pas une exception « Genesis = automatiquement vérifié ».

Je formaliserais :

$$
\boxed{
Q(H)=\min(Q_{max},H-1)
}
$$

avec :

$$
Q_{max}=100.
$$

Ainsi :

| Humains déjà vérifiés | Validations requises |
| --------------------: | -------------------: |
|                     1 | impossible / attente |
|                     2 |                    1 |
|                    10 |                    9 |
|                    25 |                   24 |
|                    50 |                   49 |
|                    99 |                   98 |
|               **100** |               **99** |
|               **101** |              **100** |
|                  102+ |              **100** |

Donc le système atteint son régime définitif à :

$$
\boxed{101\ humains vérifiés}
$$

et ensuite :

$$
\boxed{Q=100}
$$

en permanence.

Cela correspond beaucoup mieux à ta phrase :

> « Si le 1 doit attendre d'avoir 101 ou plus pour être le premier validé, il devra attendre. »

Je suis favorable à cette règle.

---

# 7. La récompense ne doit surtout pas être perdue pendant l'attente

Je conserverais :

$$
Reward_{earned}
$$

et :

$$
Reward_{transferable}.
$$

Par exemple :

```text
Utilisateur #247

HumanProof:
37 / 100

Reward earned:
0.184 ARTCB

Reward transferable:
0 ARTCB
```

Lorsque les 100 validations sont obtenues :

```text
HumanProof:
100 / 100

Reward earned:
0.184 ARTCB

Reward pending:
0.184 ARTCB
```

Puis après la période de challenge :

```text
Reward transferable:
0.184 ARTCB
```

Le fichier de simulation actuel contient déjà cette logique d'états, même si le champ `Transfert vers wallet` doit être inversé/clarifié dans la spécification finale : `VERIFIED` ne devrait pas encore signifier immédiatement « transférable » ; `MATURED` devrait être l'état de déblocage économique. 

---

# 8. Maintenant, ton idée biométrique ajoute une deuxième barrière

Et ici je modifierais légèrement l'architecture que nous avions précédemment proposée.

Tu veux deux validations :

## Validation 1 — lors de l'inscription

```text
Utilisateur
   ↓
caméra / empreinte
   ↓
biométrie
   ↓
liveness
   ↓
unicité
   ↓
HumanID candidat
```

## Validation 2 — devant un Finder

```text
Utilisateur
      ↓
Finder
      ↓
caméra
      ↓
interaction temps réel
      ↓
liveness
      ↓
questions dynamiques
      ↓
validation Finder
```

C'est beaucoup plus intéressant qu'une simple reconnaissance faciale.

---

# 9. Je séparerais quatre fonctions biométriques

Il ne faut pas demander à une seule technologie de tout faire.

### A. Détection du visage

> « Est-ce bien un visage ? »

### B. Vérification d'identité

> « Ce visage correspond-il à l'identité biométrique enregistrée ? »

### C. Liveness

> « Est-ce une personne réelle devant la caméra maintenant ? »

### D. Estimation/attestation d'âge

> « Cette personne est-elle majeure ? »

Ce sont **quatre problèmes différents**.

Et particulièrement :

$$
\boxed{
AgeEstimate\neq AgeProof
}
$$

Une IA qui estime « probablement 24 ans » ne constitue pas juridiquement une preuve suffisante de majorité.

Pour ARTCB, je recommanderais donc une **preuve d'âge distincte**, idéalement une attestation/credential vérifiable, tout en gardant le résultat d'âge hors chaîne.

---

# 10. Pour le visage : les technologies Open Source que je privilégierais

Pour ARTCB, je ne prendrais pas `face_recognition/dlib` comme technologie principale.

Je classerais plutôt :

### 1. InsightFace

Très intéressant pour :

* détection ;
* embeddings ;
* reconnaissance ;
* modèles modernes ;
* exécution locale.

### 2. OpenCV

À utiliser comme couche d'infrastructure :

* caméra ;
* prétraitement ;
* qualité image ;
* géométrie ;
* flux vidéo.

### 3. MediaPipe

Très intéressant pour :

* landmarks ;
* suivi du visage ;
* mouvements ;
* interaction temps réel.

### 4. CompreFace

Intéressant si tu veux rapidement exposer la reconnaissance sous forme de service.

---

# 11. Pour l'empreinte

Je privilégierais :

### SourceAFIS

Très intéressant pour le matching 1:1.

### NBIS

Très intéressant pour :

* extraction des minuties ;
* qualité ;
* matching ;
* référence biométrique.

Mais le point critique est celui-ci :

$$
\boxed{
biométrie\ brute\not\rightarrow blockchain
}
$$

Jamais.

---

# 12. L'identité biométrique devrait rester hors chaîne

Je proposerais :

```text
                 DEVICE
                    │
          ┌─────────┴─────────┐
          │                   │
       TPM 2.0            Biométrie
          │                   │
      DeviceID             HumanID
          │                   │
          └─────────┬─────────┘
                    │
             Crypto binding
                    │
                    ▼
                 Wallet
                    │
                    ▼
                Blockchain
```

La blockchain ne reçoit que quelque chose du type :

```text
HumanProofCommitment
DeviceProof
Attestation signatures
Nullifier
ZK proof
```

et jamais :

```text
photo.jpg
empreinte.png
face_embedding
```

---

# 13. La caméra du Finder est particulièrement intéressante

Je ne ferais pas simplement :

> « regarde la caméra ».

Je ferais une **session de challenge dynamique**.

Exemple :

```text
FINDER SESSION #8472

Challenge 1:
tournez la tête à gauche

Challenge 2:
regardez le point bleu

Challenge 3:
dites le nombre affiché

Challenge 4:
souriez

Challenge 5:
regardez la caméra

Challenge 6:
répondez à la question aléatoire
```

Le protocole génère les challenges **après le démarrage de la session**.

Cela rend beaucoup plus difficile l'utilisation d'une vidéo préenregistrée.

---

# 14. Mais attention à une chose

Le Finder ne doit pas devenir :

> « un policier qui décide subjectivement si quelqu'un est majeur ».

Il doit avoir une interface structurée :

```text
Liveness:       PASS
Face match:     PASS
Challenge:      PASS
Credential age: PASS
Session valid:  PASS
```

Puis :

$$
\boxed{FinderAttestation=VALID}
$$

ou :

$$
\boxed{FinderAttestation=REJECT}
$$

Cela rend les décisions beaucoup plus auditables.

---

# 15. Et maintenant le point intéressant : les Finders eux-mêmes doivent être vérifiés

Sinon :

```text
100 faux Finders
      ↓
100 validations
      ↓
faux humain
```

Donc :

$$
\boxed{
Finder\in HumanVerified
}
$$

doit être une condition obligatoire.

Et je rajouterais :

$$
\boxed{
Finder\_maturity > T
}
$$

Autrement dit, un nouveau compte fraîchement vérifié ne devrait pas immédiatement pouvoir valider 100 autres comptes.

---

# 16. Cela crée une profondeur de confiance

Par exemple :

```text
Genesis / bootstrap
       ↓
Human Verified
       ↓
maturation
       ↓
Finder eligible
       ↓
Finder activity
       ↓
Trust score
```

Le réseau ne dit donc pas seulement :

> « cette personne est vérifiée ».

Il dit :

> « cette personne est vérifiée depuis suffisamment longtemps et a suffisamment d'historique pour participer à la vérification d'autres humains ».

---

# 17. Coût d'une attaque Sybil

Ici il faut distinguer deux choses.

### Coût cryptographique

Avec Q=100 et proportion malveillante p :

$$
P_{attack}=p^{100}.
$$

### Coût économique

Si le réseau possède \(N\) Finders et que l'attaquant veut contrôler une fraction \(p\) :

$$
\boxed{
M\approx pN
}
$$

identités malveillantes doivent être contrôlées.

Si chaque identité Sybil coûte \(C_S\) :

$$
\boxed{
Cost_{Sybil}\approx pN C_S
}
$$

C'est cette formule que nous devons utiliser dans la prochaine simulation économique.

---

# 18. Exemple avec 1 000 Finders

Supposons :

$$
N=1000.
$$

Pour atteindre :

| Contrôle attaquant | Finders malveillants nécessaires |
| -----------------: | -------------------------------: |
|                1 % |                               10 |
|               10 % |                              100 |
|               25 % |                              250 |
|               50 % |                              500 |

Mais même avec **500/1 000 Finders malveillants**, si les 100 Finders du comité sont tirés aléatoirement :

$$
P_{false}=0.5^{100}
$$

soit :

$$
\boxed{7,89\times10^{-31}}.
$$

C'est le résultat le plus intéressant de cette simulation.

---

# 19. Mais il existe une attaque plus dangereuse que le simple pourcentage

C'est :

## **la collusion sélective**

Supposons que l'attaquant ne possède que 10 % des Finders, mais réussisse à manipuler la sélection.

Alors le modèle :

$$
p^{100}
$$

ne s'applique plus.

Il faut donc sécuriser :

$$
\boxed{RandomSelection}
$$

avec une source aléatoire que le candidat et les Finders ne peuvent pas prévoir ou manipuler.

---

# 20. Autre attaque : la compromission des Finders honnêtes

Il faut aussi modéliser :

```text
Finder honnête
      ↓
corruption financière
      ↓
validation frauduleuse
```

Donc « malveillant » ne doit pas seulement signifier :

> compte créé par l'attaquant.

Il faut tester :

$$
p_{Sybil}
$$

et :

$$
p_{corruption}.
$$

La vraie probabilité devient plutôt :

$$
\boxed{
p_{effective}
=
p_{Sybil}
+
p_{corruption}
-
p_{intersection}
}
$$

avec une modélisation plus précise ensuite.

---

# 21. Onboarding : Q=100 a un coût réel

C'est le principal inconvénient.

Avec Q=10 :

$$
10
$$

validations.

Avec Q=100 :

$$
100.
$$

Avec Q=200 :

$$
200.
$$

Donc la sécurité augmente très fortement, mais la charge humaine aussi.

La capacité théorique du réseau devient :

$$
\boxed{
NewUsers/day=
\frac{FinderCapacity/day}{Q}
}
$$

Si 10 000 Finders effectuent chacun 10 validations/jour :

$$
100\,000
$$

validations/jour.

Avec Q=100 :

$$
\boxed{1000\ nouveaux\ humains/jour}
$$

maximum théorique.

---

# 22. C'est pourquoi je ne choisirais pas Q uniquement avec la sécurité

Il faut optimiser :

$$
\boxed{
Q^*
=
argmax
\left(
Security
-
OnboardingCost
\right)
}
$$

sous contrainte :

$$
FalseConsensus<P_{target}
$$

et :

$$
OnboardingTime<T_{target}.
$$

C'est exactement la simulation que nous devons maintenant construire.

---

# 23. Mon classement provisoire

Avec **ta règle stricte**, je ne pense plus que Q=10 soit suffisamment intéressant.

### Q=10

Très rapide, mais beaucoup plus faible.

### Q=25

Déjà très robuste.

### Q=50

Excellent compromis potentiel.

### **Q=100**

Très forte sécurité, mais charge humaine élevée.

### Q=150

Gain de sécurité énorme, mais probablement rendement marginal faible.

### Q=200

Très sécurisé, mais coût d'onboarding probablement excessif.

Donc, **je soupçonne que Q=50 ou Q=100 sera le point optimal**, mais il faut le démontrer avec les données de disponibilité réelles des Finders.

---

# 24. Une amélioration que je recommande fortement

Je garderais :

$$
\boxed{Q_{security}=100}
$$

mais je permettrais une validation parallèle.

Ainsi, ce n'est pas :

```text
Finder 1
  ↓
Finder 2
  ↓
Finder 3
...
Finder 100
```

mais :

```text
             Candidate
                 │
       ┌─────────┼─────────┐
       ↓         ↓         ↓
      F1        F2        F3
       ↓         ↓         ↓
      ...       ...       ...
       └─────────┼─────────┘
                 ↓
              100/100
```

Les 100 sessions peuvent fonctionner simultanément.

C'est essentiel pour rendre Q=100 utilisable.

---

# 25. Le protocole que je recommande maintenant

```text
                    INSCRIPTION
                         │
             ┌───────────┴───────────┐
             │                       │
         Biométrie                Device
             │                       │
     Face / fingerprint             TPM
             │                       │
         Liveness                Device proof
             │                       │
             └───────────┬───────────┘
                         ↓
                    HumanID
                         │
                         ↓
                  Reward Pending
                         │
                         ↓
                 FINDER REQUEST
                         │
                         ↓
              Random Finder Selection
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
        Finder          Finder         Finder
          │              │              │
       Camera         Camera          Camera
       Liveness       Liveness        Liveness
       Challenge      Challenge       Challenge
          │              │              │
          └──────────────┼──────────────┘
                         ↓
                     Q / Q
                         │
                    Q = 100
                         │
                         ↓
                  Human VERIFIED
                         │
                  Challenge period
                         │
                         ↓
                    MATURED
                         │
                         ↓
                Reward transferable
```

---

# 26. Et la règle fondamentale devient

$$
\boxed{
HumanVerified
=
BiometricProof
\land
DeviceProof
\land
Liveness
\land
FinderQuorum
}
$$

avec :

$$
FinderQuorum=100/100
$$

dans le régime mature.

**Je trouve cette formulation nettement plus solide que notre modèle précédent.**

---

## Conclusion de la simulation

La découverte principale est que **ta règle « 100 validations obligatoires » transforme complètement le problème de sécurité**.

Avec sélection aléatoire indépendante :

$$
\boxed{P_{false}=p^{100}}
$$

et même à :

$$
p=50\%
$$

on obtient :

$$
\boxed{7,89\times10^{-31}}
$$

par comité.

En revanche, le véritable risque ne devient plus le nombre 100 lui-même, mais :

1. **la manipulation de la sélection des Finders** ;
2. **les identités Sybil utilisées pour devenir Finders** ;
3. **la collusion/corruption de Finders honnêtes** ;
4. **la disponibilité des 100 Finders** ;
5. **le coût d'onboarding**.

C'est donc exactement là que je concentrerais la prochaine simulation.

### Paramètres définitifs à tester

$$
\boxed{Q\in\{10,25,50,100,150,200\}}
$$

$$
\boxed{p_{malicious}\in[1\%,50\%]}
$$

et pour chacun :

* \(P_{false}\)
* nombre moyen de Finders nécessaires ;
* temps d'onboarding ;
* capacité maximale d'onboarding/jour ;
* nombre de Finders malveillants nécessaires ;
* coût Sybil en fonction de \(N\) ;
* coût de corruption ;
* effet d'une sélection non parfaitement aléatoire ;
* taux d'abandon des Finders ;
* disponibilité réelle du quorum.

**Je recommande donc de ne pas supprimer Q=100 : il doit rester notre scénario de sécurité de référence.** Ensuite la simulation déterminera si Q=50 offre presque la même sécurité avec un onboarding nettement meilleur, ou si Q=100 justifie réellement son coût humain.
