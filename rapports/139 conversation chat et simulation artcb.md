# Simulation ARTCB — Q=100 / Finder Block / capacité mondiale

**Simulation relancée sur le modèle de référence**, avec les paramètres que tu as verrouillés. J’ai également corrigé une incohérence importante dans le calcul du nombre de Finders enregistrés.

### Expertises mobilisées

* **Architecture blockchain / consensus**
* **Théorie des files d’attente et dimensionnement**
* **Simulation stochastique**
* **Anti-Sybil / identité humaine**
* **Cryptographie appliquée**
* **Mechanism design**
* **Tokenomics**
* **Modélisation démographique**
* **Scalabilité réseau**
* **Analyse de sécurité probabiliste**

Les documents confirment notamment le cycle `INSCRIT → FINDER_PENDING → VERIFIED → MATURED`, avec **100 attestations distinctes**, puis contrôles anti-collusion avant la finalisation.  Ils confirment également que le Finder Block redistribue une partie de la récompense PoL, sans émission supplémentaire. 

---

## 1. Paramètres verrouillés

| Paramètre                |                       Valeur |
| ------------------------ | ---------------------------: |
| Q                        |                      **100** |
| Attestations requises    |    **100 HumanID distincts** |
| Bloc de référence        |                    **600 s** |
| Capacité nominale Finder |        **20 attestations/h** |
| Disponibilité            |                     **70 %** |
| Acceptation              |                     **90 %** |
| Réussite opérationnelle  |                     **90 %** |
| Efficacité globale       |                   **56,7 %** |
| Supply max               |               **21 M ARTCB** |
| Finder Block             | **financé dans \(R_{PoL}\)** |
| HBP                      | **Human Bound Proof unique** |
| Population de référence  |                   **8,3 Md** |

---

# 2. Bootstrap Q=100

Le protocole ne peut pas s'auto-amorcer depuis zéro.

Avec :

$$
H_0<100
$$

il est mathématiquement impossible de sélectionner 100 HumanID déjà `VERIFIED`.

Le bootstrap doit donc fournir au minimum :

$$
\boxed{H_0=100}
$$

HumanID initiaux reconnus.

Ensuite :

```text
100 HumanID bootstrap
        ↓
Human #101
        ↓
100 attestations distinctes
        ↓
FINDER_PENDING
        ↓
100 attestations acceptées
        ↓
anti-collusion
        ↓
VERIFIED
        ↓
Human #101 devient potentiellement Finder
```

C'est cohérent avec le cycle d'états documenté. 

---

# 3. Capacité d'un Finder

Capacité nominale :

$$
20\times24=480
$$

attestations/jour.

Avec les trois facteurs :

$$
480\times0,70\times0,90\times0,90
$$

on obtient :

$$
\boxed{272,16}
$$

attestations utilisables/jour/Finder.

Donc :

$$
\frac{272,16}{100}
=
\boxed{2,7216}
$$

nouveaux humains/jour/Finder.

---

# 4. Scénario mondial : 8,3 Md

Avec une croissance de :

$$
0,84\%
$$

par an :

$$
8,3Md\times0,0084
=
69,72M
$$

nouveaux humains/an.

Donc :

$$
\frac{69,72M}{365}
=
\boxed{191\,013,7}
$$

nouveaux humains/jour.

Chaque nouvel humain nécessite 100 attestations :

$$
191\,013,7\times100
=
\boxed{19\,101\,370}
$$

attestations/jour.

---

# 5. Nombre de Finders réellement nécessaire

La capacité d'un Finder étant :

$$
272,16
$$

on obtient :

$$
F=
\frac{19\,101\,370}{272,16}
$$

donc :

$$
\boxed{70\,184}
$$

**Finders effectivement opérationnels.**

C'est le chiffre dimensionnant.

---

# 6. Correction importante : les 123 782 Finders

Le chiffre de **123 782 Finders enregistrés** présenté précédemment n'est pas compatible avec les mêmes facteurs appliqués deux fois.

Il faut distinguer deux modèles.

### Modèle A — 70 % représente déjà la disponibilité du Finder

Alors :

$$
480\times0,70\times0,90\times0,90
=272,16
$$

et :

$$
\boxed{70\,184}
$$

Finders enregistrés suffisent.

### Modèle B — on veut en plus une réserve de disponibilité de 70 %

Si les **70 184** sont les Finders simultanément nécessaires et que seulement 70 % du pool enregistré est disponible :

$$
F_{registered}
=
\frac{70\,184}{0,70}
$$

soit :

$$
\boxed{100\,263}
$$

Finders enregistrés.

### Donc

Je ne retiens **pas 123 782** comme chiffre de référence.

Je retiens :

$$
\boxed{70\,184\ actifs}
$$

et environ :

$$
\boxed{100\,263\ enregistrés}
$$

si l'on veut explicitement une réserve de disponibilité de 30 %.

C'est une correction importante de la simulation précédente.

---

# 7. Ratio mondial

Avec 100 263 Finders enregistrés :

$$
\frac{100\,263}{8,3Md}
=
0,001208\%
$$

soit environ :

$$
\boxed{1\ Finder/82\,800\ humains}
$$

Le réseau n'a donc pas besoin que chaque humain soit Finder.

---

# 8. Charge par Finder Block

Si un Finder Block est produit toutes les :

$$
600s=10min
$$

il y a :

$$
24\times6=144
$$

fenêtres/jour.

Donc :

$$
\frac{19\,101\,370}{144}
=
\boxed{132\,649}
$$

attestations par fenêtre en moyenne.

### Mais attention

Cela ne signifie **pas** que le bloc doit contenir 132 649 objets complets.

Les documents proposent justement un Finder Block comme **fenêtre de règlement des contributions**, avec poids et preuves, plutôt qu'un bloc représentant toute la population. 

---

# 9. Taille dynamique du Finder Block

Je conserve donc :

$$
\boxed{
B_F(t)=\min(B_{max},D_F(t)+M)
}
$$

avec :

* \(D_F(t)\) = backlog réel ;
* \(M\) = marge ;
* \(B_{max}\) = plafond protocolaire.

C'est préférable à :

$$
B_F\propto H
$$

car 8,3 Md humains ne signifient pas 8,3 Md transactions Finder.

Le document recommande également une taille dynamique plutôt qu'une taille fixe. 

---

# 10. Simulation des cinq niveaux

En conservant les hypothèses de croissance données :

| Humains vérifiés | Croissance annuelle | Nouveaux/jour | Attestations/jour | Finders actifs nécessaires |
| ---------------: | ------------------: | ------------: | ----------------: | -------------------------: |
|              1 M |                 2 % |          54,8 |             5 479 |                   **20,1** |
|             10 M |                 2 % |         547,9 |            54 795 |                  **201,3** |
|            100 M |               1,5 % |       4 109,6 |           410 959 |                **1 510,0** |
|             1 Md |                 1 % |      27 397,3 |           2,740 M |               **10 066,6** |
|           8,3 Md |              0,84 % |     191 013,7 |          19,101 M |               **70 184,3** |

La croissance de la capacité nécessaire est donc **linéaire avec le flux de nouveaux humains**, et non avec la population totale.

---

# 11. Résultat très intéressant : Q=100 n'est pas le problème

La condition de stabilité est :

$$
100N_{new}
\leq
272,16F
$$

donc :

$$
\boxed{
F\geq\frac{100N_{new}}{272,16}
}
$$

À 8,3 Md :

$$
\boxed{F\geq70\,184}
$$

Le facteur critique n'est donc pas directement :

$$
Q=100
$$

mais :

$$
\boxed{N_{new}(t)}
$$

et la capacité réelle des Finders.

---

# 12. Nouveau test : que se passe-t-il si la capacité Finder est différente ?

À 8,3 Md :

| Capacité nominale | Finders actifs nécessaires |
| ----------------: | -------------------------: |
|               5/h |                **280 737** |
|              10/h |                **140 369** |
|              20/h |                 **70 184** |
|              50/h |                 **28 074** |
|             100/h |                 **14 037** |

C'est probablement **le paramètre expérimental le plus important à mesurer dans le prototype**.

Q=100 est une règle protocolaire.

Les 20 attestations/h sont une hypothèse opérationnelle.

---

# 13. Test de bootstrap dynamique

Voici une découverte importante.

Si les nouveaux humains `VERIFIED` deviennent eux-mêmes Finders, la capacité du réseau augmente automatiquement.

Avec :

$$
2,7216
$$

nouveaux humains/jour/Finder, le système possède une dynamique de croissance potentiellement très forte.

À titre théorique, avec **100 Finders bootstrap** :

$$
100\times2,7216
=
272,16
$$

nouveaux humains/jour.

Puis ces nouveaux humains peuvent eux-mêmes augmenter le pool Finder.

Dans un modèle idéal où **chaque humain vérifié devient immédiatement Finder**, le passage de 100 à environ 70 000 Finders serait de l'ordre de :

$$
\boxed{2,4\ jours}
$$

selon le modèle exponentiel simplifié.

**Ce résultat ne doit pas être pris comme une prédiction opérationnelle** : il suppose que tous les humains deviennent Finders, sans limite de participation, sans latence, sans conflits de sélection et sans contrainte réseau.

Mais il démontre quelque chose de très intéressant :

> **ARTCB possède potentiellement une capacité d'onboarding auto-amplificatrice.**

C'est un élément à tester séparément.

---

# 14. Q=100 et collusion

Pour une fraction malveillante \(p\), si les 100 Finders sont sélectionnés indépendamment de manière uniforme, la probabilité que les 100 soient compromis est approximativement :

$$
P_{100}=p^{100}
$$

### Résultats

| Fraction compromise |            \(p^{100}\) |
| ------------------: | ---------------------: |
|                 1 % |          \(10^{-200}\) |
|                 5 % | \(7,9\times10^{-131}\) |
|                10 % |          \(10^{-100}\) |
|                25 % |  \(6,2\times10^{-61}\) |
|                50 % |  \(7,9\times10^{-31}\) |
|                90 % |  \(2,66\times10^{-5}\) |
|                99 % |             **36,6 %** |

Le dernier cas est fondamental.

Q=100 fournit une très forte protection **tant que l'adversaire reste minoritaire dans le pool**.

Mais :

$$
p\rightarrow1
$$

finit par détruire cette protection.

Le document de simulation arrive à la même conclusion qualitative : Q=100 ne remplace pas la résistance à la compromission du pool entier. 

---

# 15. Le vrai test de sécurité doit aller plus loin

La prochaine simulation de sécurité doit donc tester :

$$
(Q,p,N,\rho,R)
$$

où :

* \(Q=100\) : taille du comité ;
* \(p\) : fraction malveillante ;
* \(N\) : taille du pool Finder ;
* \(\rho\) : qualité de la randomisation ;
* \(R\) : règles de remplacement/rotation.

Et surtout, il faut distinguer :

### Attaque 1

Les 100 sont malveillants.

$$
p^{100}
$$

### Attaque 2

Une majorité des 100 est malveillante.

### Attaque 3

Un attaquant contrôle plusieurs HumanID.

### Attaque 4

Collusion entre Finders légitimes.

### Attaque 5

Indisponibilité simultanée des Finders.

### Attaque 6

Création massive de HBP invalides.

Le protocole doit résister à ces scénarios séparément.

---

# 16. Finder Block : récompense

La structure reste :

$$
\boxed{
R_{PoL}=R_M+R_F
}
$$

avec :

$$
R_F=P_F(H)R_{PoL}
$$

et :

$$
R_M=(1-P_F(H))R_{PoL}.
$$

Donc :

$$
\boxed{
R_F+R_M=R_{PoL}
}
$$

Il n'y a **aucune nouvelle émission**.

Le Finder Block est donc un mécanisme d'allocation, pas une source monétaire indépendante. 

---

# 17. Allocation aux Finders

Je conserve le poids :

$$
W_i=N_iQ_iU_iC_i
$$

où :

* \(N_i\) = HBP valides ;
* \(Q_i\) = qualité ;
* \(U_i\) = unicité ;
* \(C_i\) = confiance/contribution.

Puis :

$$
\boxed{
Reward_i=
R_F\frac{W_i}{\sum_jW_j}
}
$$

Le document recommande précisément cette approche plutôt qu'un simple comptage brut des personnes. 

---

# 18. Exemple à \(R_F=0,60\)

Avec :

$$
W_A=100,\quad W_B=10,\quad W_C=3
$$

on obtient :

$$
W_{total}=113
$$

et :

$$
A=0,53097
$$

$$
B=0,05310
$$

$$
C=0,01593.
$$

La somme reste exactement :

$$
\boxed{0,60\ ARTCB}
$$

comme le prévoit le modèle Finder Block. 

---

# 19. Résultat global de la simulation

## À 8,3 milliards

$$
\boxed{191\,014\ nouveaux\ humains/jour}
$$

$$
\boxed{19,101\ millions\ attestations/jour}
$$

$$
\boxed{70\,184\ Finders\ effectivement\ nécessaires}
$$

$$
\boxed{\approx100\,263\ Finders\ enregistrés}
$$

si l'on ajoute une réserve de disponibilité de 30 % **en plus** des pertes/refus déjà intégrés.

Et :

$$
\boxed{132\,649\ attestations/10\,minutes}
$$

en moyenne.

---

# 20. Verdict technique

### Je valide le modèle comme **dimensionnable**, avec quatre réserves.

**1. Q=100 est viable.**

Il ne constitue pas en lui-même le goulet d'étranglement.

**2. Le Finder Block dynamique est préférable.**

Il règle la demande réelle plutôt que la population totale.

**3. L'hypothèse 20 attestations/h doit être expérimentée.**

C'est actuellement une hypothèse de capacité, pas une propriété démontrée du protocole.

**4. Le bootstrap doit être explicitement protocolisé.**

Minimum :

$$
\boxed{100\ HumanID\ bootstrap}
$$

puis fonctionnement normal Q=100.

---

## Point nouveau à retenir

La simulation fait apparaître **deux architectures possibles**, très différentes :

```text
MODE A
100 bootstrap
     ↓
petit pool Finder fixe
     ↓
augmentation progressive du pool
     ↓
dimensionnement à ~70k actifs
```

ou :

```text
MODE B
100 bootstrap
     ↓
chaque VERIFIED devient Finder
     ↓
capacité auto-amplificatrice
     ↓
le réseau dépasse rapidement la demande mondiale
```

**Le choix entre A et B est maintenant un paramètre architectural majeur d'ARTCB.** Il mérite une simulation dédiée, car il peut modifier radicalement le temps d'onboarding mondial et le nombre réel de Finders nécessaires.

Je peux maintenant lancer la **simulation Monte-Carlo complète sur 365 jours**, avec bootstrap de 100 HumanID, croissance quotidienne, Finders actifs/inactifs, refus, pertes, backlog, remplacement automatique et taux de collusion de 1 % à 99 %.
