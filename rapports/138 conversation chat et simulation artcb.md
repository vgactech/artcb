# Simulation ARTCB — Q=100 / Finder Block / capacité mondiale

**Simulation relancée.** Je conserve les paramètres que tu as verrouillés et je distingue les résultats directement calculables des hypothèses de modèle. Les documents ARTCB confirment notamment que le Finder Block est financé **à l'intérieur** de la récompense PoL et que les contributions doivent être liées à des `HumanID` uniques, et non à de simples clics/invitations.  

### Expertises mobilisées

* Consensus distribué
* Théorie des files d'attente
* Dimensionnement blockchain
* Anti-Sybil / identité humaine
* Cryptographie appliquée
* Probabilités / hypergéométrie
* Mechanism design
* Tokenomics
* Modélisation démographique
* Scalabilité réseau

---

## 1. Paramètres de référence

Je verrouille :

| Paramètre               |                    Valeur |
| ----------------------- | ------------------------: |
| **Q**                   |                   **100** |
| Validations nécessaires | **100 HumanID distincts** |
| Temps de référence      |                 **600 s** |
| Capacité brute Finder   |     **20 attestations/h** |
| Disponibilité           |                  **70 %** |
| Refus                   |                  **10 %** |
| Perte opérationnelle    |                  **10 %** |
| Efficacité globale      |                **56,7 %** |
| Capacité nominale       |       **480/jour/Finder** |
| Capacité effective      |    **272,16/jour/Finder** |
| Supply maximum          |            **21 M ARTCB** |
| Finder Block            | **redistribution de PoL** |

La logique documentée est bien :

$$
\boxed{R_{PoL}=R_{Miner}+R_{Finder}}
$$

et non une émission supplémentaire. 

---

# 2. Première correction : le démarrage du réseau

Il y a un point logique que la simulation précédente ne faisait pas suffisamment ressortir.

Si la règle est absolument :

$$
\boxed{\text{chaque nouvel humain doit recevoir 100 validations de 100 humains déjà VERIFIED}}
$$

alors le protocole ne peut **pas** démarrer avec 1 seul humain.

Pour le premier humain :

$$
N_{verified}=0
$$

donc il est impossible d'obtenir :

$$
100\ validations
$$

à partir du réseau lui-même.

### Il faut donc un bootstrap

Le modèle cohérent est :

```text
GENESIS / BOOTSTRAP
        │
        ▼
100 HumanID initialement reconnus
        │
        ▼
       Q=100
        │
        ▼
Humain #101
        │
        ▼
100 Finders parmi les 100+ VERIFIED
        │
        ▼
Humain #101 VERIFIED
        │
        ▼
Humain #102
        │
        ▼
...
```

**Après le bootstrap**, la règle Q=100 devient universelle.

C'est une contrainte mathématique du protocole, pas une faiblesse particulière d'ARTCB.

---

# 3. Capacité réelle d'un Finder

Calcul :

$$
20\times24=480
$$

attestations nominales/jour.

Puis :

$$
480\times0,70\times0,90\times0,90
=
\boxed{272,16}
$$

attestations effectivement utilisables par jour.

Donc un Finder effectif peut valider en moyenne :

$$
\boxed{272,16/100=2,7216}
$$

**nouveaux humains complets par jour**, si toute sa capacité est consacrée à l'onboarding.

---

# 4. Simulation mondiale

J'ai recalculé les cinq niveaux avec exactement tes paramètres.

| Humains vérifiés | Croissance/an | Nouveaux humains/jour | Validations nécessaires/jour | Finders effectifs | Finders enregistrés |
| ---------------: | ------------: | --------------------: | ---------------------------: | ----------------: | ------------------: |
|          **1 M** |           2 % |                 54,79 |                        5 479 |         **20,13** |              **36** |
|         **10 M** |           2 % |                547,95 |                       54 795 |        **201,33** |             **356** |
|        **100 M** |         1,5 % |              4 109,59 |                      410 959 |      **1 509,99** |           **2 664** |
|         **1 Md** |           1 % |             27 397,26 |                      2,740 M |     **10 066,60** |          **17 755** |
|       **8,3 Md** |        0,84 % |            191 013,70 |                 **19,101 M** |     **70 184,34** |         **123 782** |

Les valeurs précédentes sont donc confirmées à l'arrondi près.

### Résultat mondial

$$
\boxed{
F_{effectif}\approx70\,184
}
$$

et avec l'efficacité d'enregistrement :

$$
\boxed{
F_{registered}\approx123\,782
}
$$

pour une population de :

$$
\boxed{8,3\ milliards}
$$

---

# 5. Ce que cela signifie réellement

Le chiffre de **123 782 Finders** peut sembler important, mais rapporté à 8,3 milliards :

$$
\frac{123\,782}{8,3\times10^9}
\approx0,00149\%
$$

soit environ :

$$
\boxed{1\ Finder\ enregistré/67\,100\ humains}
$$

C'est donc une fraction extrêmement faible de la population.

Le protocole n'a pas besoin que tout le monde soit Finder.

---

# 6. Charge du Finder Block

Avec 144 périodes de 10 minutes par jour :

$$
\frac{19\,101\,370}{144}
=
\boxed{132\,648}
$$

validations à traiter par fenêtre de 10 minutes au scénario 8,3 Md.

| Population | Validations / 10 min |
| ---------: | -------------------: |
|        1 M |               **38** |
|       10 M |              **381** |
|      100 M |            **2 854** |
|       1 Md |           **19 026** |
|     8,3 Md |          **132 648** |

Le document ARTCB converge précisément vers cette idée : le Finder Block doit être une **fenêtre de règlement des contributions**, et non un bloc contenant la totalité de la population. 

---

# 7. Finder Block dynamique

Je conserve donc :

$$
\boxed{
B_F(t)=f(D_F(t))
}
$$

où \(D_F(t)\) représente la demande réelle en attente.

Le document propose explicitement une taille dynamique avec plafond, plutôt qu'une taille proportionnelle naïvement au nombre total d'humains. 

Je retiens donc :

$$
\boxed{
B_F(t)=\min(B_{max},D_F(t)+M)
}
$$

avec :

* \(D_F(t)\) = backlog réel ;
* \(M\) = marge ;
* \(B_{max}\) = limite de sécurité du bloc.

C'est préférable à :

$$
B_F\propto H
$$

car la blockchain ne traite que les **preuves effectivement produites**, pas tous les humains existants.

---

# 8. Test de stabilité du réseau

La condition fondamentale devient :

$$
Capacity_F(t)\geq Demand_F(t)
$$

donc :

$$
272,16F(t)\geq100N_{new}(t)
$$

et par conséquent :

$$
\boxed{
F(t)\geq
\frac{100N_{new}(t)}{272,16}
}
$$

C'est la formule de dimensionnement principale.

À 8,3 Md :

$$
F_{min}=70\,184,34
$$

Finders actifs.

Avec la marge de 25 % proposée précédemment :

$$
70\,184\times1,25
\approx
\boxed{87\,730}
$$

Finders effectivement disponibles.

Et si on conserve 56,7 % de disponibilité des inscrits :

$$
\frac{87\,730}{0,567}
\approx
\boxed{154\,700}
$$

Finders enregistrés.

Donc le pool opérationnel recommandé devient environ :

$$
\boxed{155\,000}
$$

à pleine échelle.

---

# 9. Q=100 : simulation de collusion

C'est ici que Q=100 devient très puissant.

Si le comité est sélectionné aléatoirement parmi un pool suffisamment grand, et si une fraction \(p\) du pool est malveillante, l'approximation de la probabilité que **les 100 membres sélectionnés soient tous malveillants** est :

$$
P_{100}\approx p^{100}.
$$

### Résultats

| Finders malveillants |            \(p^{100}\) |
| -------------------: | ---------------------: |
|              **1 %** |          \(10^{-200}\) |
|              **5 %** | \(7,9\times10^{-131}\) |
|             **10 %** |          \(10^{-100}\) |
|             **25 %** |  \(6,2\times10^{-61}\) |
|             **50 %** |  \(7,9\times10^{-31}\) |
|             **99 %** |   \(3,7\times10^{-1}\) |

Le dernier résultat est particulièrement important.

### À 99 % de Finders compromis

$$
0,99^{100}\approx36,6\%
$$

Donc **Q=100 ne protège pas contre un réseau dont presque tout le pool est compromis**.

C'est une propriété fondamentale.

Q=100 protège contre une **minorité malveillante sélectionnée aléatoirement** ; il ne crée pas magiquement de l'honnêteté lorsque 99 % du comité est hostile.

---

# 10. Le seuil critique est donc différent

Le vrai paramètre de sécurité n'est pas seulement :

$$
Q=100.
$$

C'est :

$$
\boxed{
(Q,\ p,\ N,\ randomisation,\ identité)
}
$$

avec :

* \(Q\) = taille du comité ;
* \(p\) = fraction compromise ;
* \(N\) = taille du pool ;
* randomisation = qualité de la sélection ;
* identité = résistance à la création de faux humains.

C'est beaucoup plus important que de simplement annoncer « Q=100 ».

---

# 11. Une nouvelle découverte : 100 validations ne signifie pas 100 connexions permanentes

Le protocole ne devrait pas demander :

```text
Nouvel humain
     │
     ├── connexion permanente Finder 1
     ├── connexion permanente Finder 2
     ├── ...
     └── connexion permanente Finder 100
```

Ce serait inutilement coûteux.

Il devrait demander :

```text
HumanID nouveau
       │
       ▼
Comité aléatoire de 100
       │
       ▼
100 attestations signées
       │
       ▼
Commitment / Merkle root
       │
       ▼
FINDER BLOCK
       │
       ▼
FINDER_PENDING
       │
       ▼
VERIFIED
```

Cela correspond mieux à l'architecture de Finder Block déjà développée dans les fichiers. 

---

# 12. Anti-répétition : point critique

Le fichier apporte une contrainte très importante :

> il faut comptabiliser le **Human Bound Proof unique**, et non le nombre de clics/invitations. 

Donc :

$$
\boxed{
Contribution=HBP(HumanID_{new},FinderID,epoch)
}
$$

mais une seconde contribution du même Finder pour le même humain ne doit pas augmenter artificiellement son poids.

Sinon :

```text
Finder A
   ↓
même HumanID
   ↓
100 000 attestations
```

pourrait devenir une attaque économique.

---

# 13. Récompense Finder

Je conserve la formule documentée :

$$
R_F=P_F(H)\times R_{PoL}
$$

puis :

$$
R_M=(1-P_F(H))R_{PoL}.
$$

Et pour chaque Finder :

$$
Reward_i=
R_F
\frac{W_i}{\sum_jW_j}.
$$

Le document recommande précisément de ne pas utiliser uniquement le nombre brut de contributions, mais un poids combinant nombre de HBP valides, qualité, unicité et confiance/contribution. 

---

# 14. Exemple à pleine échelle

Prenons :

$$
R_F=0,60\ ARTCB
$$

pour un Finder Block.

Supposons :

$$
W_A=100
$$

$$
W_B=10
$$

$$
W_C=3.
$$

Alors :

$$
W_{total}=113
$$

et :

$$
A=0,60\times\frac{100}{113}
=0,53097
$$

$$
B=0,05310
$$

$$
C=0,01593.
$$

C'est exactement la logique proportionnelle retenue dans la simulation. 

---

# 15. Le Finder Block ne doit pas obligatoirement être plein

Autre conséquence importante.

Supposons que :

$$
R_F=0,60
$$

mais qu'un bloc ne contienne que 40 % de la capacité maximale.

Il ne faut pas inventer des contributions.

Le protocole doit pouvoir :

$$
R_F\rightarrow Treasury
$$

puis :

$$
Treasury\rightarrow FinderBlock
$$

selon les contributions effectivement admissibles. Cette architecture de trésorerie est déjà envisagée dans les documents. 

---

# 16. Le résultat économique est donc meilleur que le modèle « bloc géant »

On obtient :

```text
                  HUMANID
                     │
                     ▼
             demande d'attestation
                     │
                     ▼
             sélection aléatoire
                     │
                     ▼
               100 Finders
                     │
                     ▼
             100 attestations
                     │
                     ▼
              HBP commitment
                     │
                     ▼
               Finder Block
                     │
             ┌───────┴───────┐
             ▼               ▼
          Miner           Finders
             │               │
             └────── PoL ────┘
                     │
                     ▼
              Reward PoL
```

Le tout reste :

$$
\boxed{R_{Miner}+R_{Finder}=R_{PoL}}
$$

donc sans inflation supplémentaire.

---

# 17. Verdict de la simulation

## Q=100 est techniquement dimensionnable

À partir des hypothèses actuellement fixées :

$$
\boxed{
Q=100
}
$$

n'est **pas le facteur qui bloque la scalabilité**.

Le véritable facteur dimensionnant est :

$$
\boxed{
N_{new}(t)
}
$$

c'est-à-dire le flux de nouveaux humains.

Le protocole doit simplement maintenir :

$$
\boxed{
F(t)\geq
\frac{100N_{new}(t)}{272,16}
}
$$

avec une marge opérationnelle.

---

## À 8,3 milliards

On obtient :

$$
\boxed{191\,014\ nouveaux\ humains/jour}
$$

$$
\boxed{19,10\ millions\ attestations/jour}
$$

$$
\boxed{70\,184\ Finders\ actifs\ nécessaires}
$$

$$
\boxed{123\,782\ Finders\ enregistrés\ minimum}
$$

ou environ :

$$
\boxed{155\,000}
$$

avec une marge opérationnelle de 25 %.

Et chaque Finder Block de 10 minutes doit traiter en moyenne :

$$
\boxed{132\,648\ attestations}
$$

**si** on conserve une fréquence d'un Finder Block toutes les 10 minutes.

---

# 18. Point critique à tester maintenant

Le résultat le plus important de cette simulation n'est finalement pas le nombre de Finders.

C'est cette hypothèse :

$$
\boxed{20\ attestations/h/Finder}
$$

Elle détermine presque directement toute l'architecture.

Par exemple :

| Capacité réelle | Finders enregistrés nécessaires à 8,3 Md |
| --------------: | ---------------------------------------: |
|         **5/h** |                                 ~495 000 |
|        **10/h** |                                 ~247 600 |
|        **20/h** |                              **123 782** |
|        **50/h** |                                  ~49 500 |
|       **100/h** |                                  ~24 800 |

Donc **Q=100 est relativement robuste ; la capacité humaine réelle des Finders est beaucoup plus incertaine.**

### Conclusion

Je valide donc la nouvelle architecture de simulation :

$$
\boxed{
Q=100
+
HumanID\ unique
+
100\ Finders\ aléatoires
+
Finder\ Block\ dynamique
+
Merkle/commitment
+
PoL\rightarrow Miner+Finder
+
pool\ Finder\ dynamique
}
$$

avec une réserve essentielle : **le bootstrap des 100 premiers HumanID doit être spécifié explicitement**, car Q=100 ne peut pas s'auto-amorcer à partir de zéro.

Je peux maintenant lancer la **simulation Monte-Carlo complète du protocole Q=100**, avec 1 %, 5 %, 10 %, 25 %, 50 % et 99 % de Finders malveillants, backlog dynamique, remplacement des Finders indisponibles et temps réel d'onboarding de 1 à 8,3 milliards d'humains.
