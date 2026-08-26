# Simulation ARTCB — Q=100 / Finder Block / capacité mondiale

J’ai lancé la **nouvelle simulation combinée** à partir des règles présentes dans les documents ARTCB, en conservant **Q=100** et en corrigeant une incohérence numérique de la simulation précédente.

Le fichier de référence confirme que `FINDER_PENDING` exige **100 attestations distinctes**, puis `VERIFIED` exige 100 attestations acceptées avec contrôles anti-collusion.  Le Finder Block reste financé **à l’intérieur de la récompense PoL**, sans émission supplémentaire. 

## Expertises mobilisées

* Consensus distribué et sélection de comité
* Anti-Sybil / identité humaine
* Théorie des files d’attente
* Dimensionnement réseau
* Scalabilité blockchain
* Mechanism design
* Tokenomics
* Probabilités / simulation de collusion
* Modélisation démographique

---

# 1. Paramètres verrouillés

| Paramètre                           |                                   Valeur |
| ----------------------------------- | ---------------------------------------: |
| **Q**                               |                                  **100** |
| Attestations requises               |                **100 HumanID distincts** |
| Bloc de référence                   |                                **600 s** |
| Attestations/Finder                 |                                 **20/h** |
| Disponibilité                       |                                 **70 %** |
| Refus                               |                                 **10 %** |
| Neutralisation/perte opérationnelle |                                 **10 %** |
| Efficacité globale                  |                               **56,7 %** |
| Capacité nominale/Finder            |                    480 attestations/jour |
| Capacité effective/Finder           |                          **272,16/jour** |
| Supply maximal                      |                           **21 M ARTCB** |
| HBP/Finder                          | redistribué depuis PoL, pas créé en plus |

La règle économique existante est bien :

$$
R_{PoL}=R_{Miner}+R_{Finder}
$$

et non :

$$
R_{PoL}+R_{Finder}.
$$



---

# 2. Correction importante de la simulation précédente

La précédente estimation annonçait environ **20 Finders enregistrés pour 1 M d'humains**.

Ce chiffre était sous-estimé.

Avec les hypothèses réellement écrites :

$$
20\times24=480
$$

attestations nominales/jour/Finder.

Puis :

$$
480\times0,70\times0,90\times0,90
=
272,16
$$

attestations effectives/jour/Finder.

À 1 M d'humains avec 2 % de croissance :

$$
1\,000\,000\times0,02/365
=
54,79
$$

nouveaux humains/jour.

Il faut donc :

$$
54,79\times100
=
5\,479
$$

attestations/jour.

Et :

$$
5\,479/272,16
=
20,13
$$

**Finders effectivement disponibles**.

Mais pour obtenir ces 20,13 Finders effectifs avec seulement 56,7 % d'efficacité :

$$
20,13/0,567
=
\boxed{35,5}
$$

Finders enregistrés.

### Donc le chiffre corrigé est :

$$
\boxed{\sim36\ Finders}
$$

et non 20.

---

# 3. Résultat complet

| Population vérifiée | Croissance/an | Nouveaux humains/jour | Attestations/jour | Finders effectifs | Finders enregistrés nécessaires |
| ------------------: | ------------: | --------------------: | ----------------: | ----------------: | ------------------------------: |
|             **1 M** |           2 % |                    55 |             5 479 |                20 |                          **36** |
|            **10 M** |           2 % |                   548 |            54 795 |               201 |                         **356** |
|           **100 M** |         1,5 % |                 4 110 |           410 959 |             1 510 |                       **2 663** |
|            **1 Md** |           1 % |                27 397 |            2,74 M |            10 067 |                      **17 754** |
|          **8,3 Md** |        0,84 % |               191 014 |           19,10 M |            70 184 |                     **123 782** |

### Résultat majeur

À pleine échelle :

$$
\boxed{8,3\ Md\ humains}
$$

nécessitent, avec **20 attestations/h/Finder** et nos hypothèses opérationnelles :

$$
\boxed{\approx70\,184\ Finders\ effectivement\ disponibles}
$$

ou environ :

$$
\boxed{123\,782\ Finders\ enregistrés}
$$

pour absorber les indisponibilités, refus et pertes.

C'est plus conservateur que l'estimation précédente de 70 000 Finders enregistrés, mais **le mécanisme reste scalable**.

---

# 4. Charge d'un Finder Block de 600 secondes

Avec 144 fenêtres de 10 minutes par jour :

| Population | Attestations/jour | Attestations/10 min |
| ---------: | ----------------: | ------------------: |
|        1 M |             5 479 |              **38** |
|       10 M |            54 795 |             **381** |
|      100 M |           410 959 |           **2 854** |
|       1 Md |            2,74 M |          **19 026** |
|     8,3 Md |           19,10 M |         **132 648** |

Donc à 8,3 Md :

$$
\boxed{\sim132\,648\ attestations/Finder\ Block}
$$

en moyenne si le Finder Block règle les contributions toutes les 10 minutes.

C'est précisément pourquoi le fichier propose une **taille dynamique** plutôt qu'un bloc dimensionné directement sur la population. 

---

# 5. Le Finder Block dynamique passe le test

Je conserve :

$$
B_F(t)=f(D_F(t))
$$

où \(D_F(t)\) est la demande réelle de preuves en attente.

Donc :

### 1 M

Pas besoin d'un bloc gigantesque :

$$
\sim38
$$

attestations/10 min.

### 100 M

$$
\sim2\,854
$$

### 1 Md

$$
\sim19\,026
$$

### 8,3 Md

$$
\sim132\,648
$$

Le protocole peut donc augmenter la capacité **en fonction du backlog**, plutôt que d'inscrire les 8,3 milliards d'humains dans chaque bloc.

C'est cohérent avec l'architecture déjà proposée dans les fichiers. 

---

# 6. Pool recommandé

Je ne recommande toujours pas de fonctionner au strict minimum.

Je prends une marge d'environ 25 % :

| Population | Minimum calculé |     Pool recommandé |
| ---------: | --------------: | ------------------: |
|        1 M |              36 |           **45–50** |
|       10 M |             356 |         **450–500** |
|      100 M |           2 663 |     **3 300–3 500** |
|       1 Md |          17 754 |   **22 000–25 000** |
|     8,3 Md |         123 782 | **155 000 environ** |

Mais cela ne signifie absolument pas que chaque nouveau membre contacte 155 000 personnes.

Le protocole sélectionne :

$$
\boxed{100}
$$

Finders parmi le pool.

---

# 7. Sélection aléatoire : indispensable

Le mécanisme devient :

```text
                 Nouveau HumanID
                       │
                       ▼
                 Seed du bloc
                       │
                       ▼
             sélection aléatoire
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
         F17          F942         F...
          │            │            │
          └────────────┴────────────┘
                       │
                 100 attestations
                       │
                       ▼
                    VERIFIED
```

Le nouvel inscrit **ne choisit pas ses 100 Finders**.

Sinon l'attaquant pourrait construire artificiellement un comité favorable.

---

# 8. Test de collusion Q=100

Supposons maintenant un pool de :

$$
N=120\,000
$$

Finders.

L'attaquant contrôle :

| Part malveillante | Probabilité approximative que les **100/100** sélectionnés soient malveillants |
| ----------------: | -----------------------------------------------------------------------------: |
|           **1 %** |                                                                 ~\(10^{-202}\) |
|          **10 %** |                                                                 ~\(10^{-100}\) |
|          **25 %** |                                                                  ~\(10^{-60}\) |
|          **50 %** |                                                                  ~\(10^{-30}\) |

Ces probabilités correspondent au cas très strict où l'attaquant doit contrôler **les 100 Finders sélectionnés**.

C'est exactement pourquoi Q=100 devient beaucoup plus intéressant avec un grand pool.

### Mais attention

Cela ne prouve pas que le protocole est invulnérable.

Il faut encore empêcher :

* l'achat d'identités humaines ;
* la coercition ;
* la collusion organisée ;
* la compromission de Finders honnêtes ;
* les attaques sur la sélection aléatoire ;
* les attaques sur l'identité HumanID ;
* les faux refus coordonnés.

La cryptographie réduit fortement le problème Sybil, mais ne résout pas automatiquement la couche sociale.

---

# 9. Nouveau résultat très important : Q=100 ne limite pas la capacité

Le calcul montre quelque chose de structurel.

La charge totale est :

$$
C(t)=100\times N_{new}(t)
$$

mais la capacité est :

$$
Capacity(t)=F(t)\times272,16.
$$

Donc la condition de stabilité est :

$$
\boxed{
F(t)\geq
\frac{100N_{new}(t)}{272,16}
}
$$

Il suffit donc d'augmenter le **pool de Finders** lorsque le débit d'inscription augmente.

On ne touche pas à :

$$
\boxed{Q=100}.
$$

---

# 10. Le Finder Block et la récompense 10 → 60 → 20

Je conserve également le modèle déjà présent dans la simulation :

$$
\boxed{10\%\rightarrow60\%\rightarrow20\%}
$$

La récompense Finder reste :

$$
R_F=P_F(H)\times R_{PoL}.
$$

Puis :

$$
R_M=(1-P_F(H))R_{PoL}.
$$

Le document de simulation insiste précisément sur le fait que le HBP est une **redistribution de la récompense existante et non une inflation supplémentaire**. 

---

# 11. Répartition entre Finders

La formule proportionnelle reste valide :

$$
Reward_i
=
R_F
\frac{W_i}{\sum W}.
$$

Avec :

$$
W_i=N_i\times Q_i\times U_i\times C_i
$$

plutôt que simplement le nombre brut de validations. Cette protection est déjà proposée dans le document. 

Ainsi, un Finder ne peut pas simplement gagner toute la récompense en générant artificiellement un grand nombre de clics.

---

# 12. Ce que la simulation démontre réellement

Je sépare maintenant clairement **résultat démontré** et **hypothèse**.

### Démontré par le modèle

$$
\boxed{Q=100\ est\ compatible\ avec\ une\ population\ mondiale}
$$

à condition que :

1. le pool Finder augmente avec la demande ;
2. les 100 Finders soient sélectionnés aléatoirement ;
3. les attestations soient batchées ;
4. le Finder Block soit dynamique ;
5. les preuves soient engagées cryptographiquement plutôt que toutes incorporées naïvement dans chaque bloc.

### Pas encore démontré expérimentalement

Le chiffre :

$$
20\ attestations/heure/Finder
$$

reste une **hypothèse**.

C'est actuellement la plus grosse incertitude de cette simulation.

Si la vraie capacité est 100/h, le dimensionnement chute d'un facteur 5.

Si elle est 5/h, il est multiplié par 4.

---

# 13. Verdict de cette nouvelle simulation

Je confirme donc le choix :

$$
\boxed{\mathbf{Q=100}}
$$

Je **ne réduirais pas Q à 50 pour résoudre la scalabilité**.

La bonne solution est :

$$
\boxed{
Q=100
+
Pool\ Finder\ dynamique
+
sélection\ aléatoire
+
100\ HumanID\ distincts
+
remplacement\ automatique
+
Finder\ Block\ dynamique
+
batching
+
Merkle/commitment
+
traitement\ parallèle
}
$$

Et surtout, la simulation corrigée donne un ordre de grandeur mondial de :

$$
\boxed{\sim124\,000\ Finders\ enregistrés}
$$

dans notre scénario conservateur à 8,3 milliards, et non des centaines de millions ou des milliards.

**Prochaine étape décisive :** je peux maintenant lancer la simulation Monte-Carlo complète de **Q=100 avec 1 %, 5 %, 10 %, 25 % et 50 % de Finders malveillants**, en mesurant simultanément faux consensus, temps d'onboarding, backlog, capacité du Finder Block et coût d'une attaque Sybil.
