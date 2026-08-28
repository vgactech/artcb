# Simulation ARTCB relancée — Q=100 / Finder Block / capacité mondiale

J’ai lancé la **simulation de référence sur 365 jours**, en conservant tes paramètres verrouillés et en séparant les deux architectures que tu proposes :

* **Mode A : pool Finder dimensionné**
* **Mode B : chaque humain VERIFIED devient lui-même Finder**

La simulation confirme un résultat important : **le Mode B change complètement le problème de capacité**.

### Expertises mobilisées

* Architecture blockchain / consensus
* Théorie des files d’attente
* Simulation dynamique
* Scalabilité distribuée
* Anti-Sybil / HumanID
* Mechanism design
* Tokenomics
* Démographie
* Analyse probabiliste de sécurité

Les fichiers ARTCB confirment bien que `FINDER_PENDING` repose sur **100 attestations distinctes**, puis `VERIFIED` sur 100 attestations acceptées avec contrôle anti-collusion.  Le classeur de bootstrap recommande toutefois une **cohorte Genesis de 101 humains**, puis l'application stricte du quorum de 100 à partir du 102e humain : je signale donc cette différence avec ton paramètre verrouillé H₀=100. 

---

# 1. Paramètres effectivement simulés

| Paramètre                    |                              Valeur |
| ---------------------------- | ----------------------------------: |
| Q                            |                             **100** |
| Attestations / nouvel humain |                             **100** |
| Bloc                         |                           **600 s** |
| Capacité nominale Finder     |               **20 attestations/h** |
| Disponibilité                |                            **70 %** |
| Acceptation                  |                            **90 %** |
| Réussite opérationnelle      |                            **90 %** |
| Capacité effective           | **272,16 attestations/jour/Finder** |
| Population de référence      |                          **8,3 Md** |
| Croissance mondiale utilisée |                       **0,84 %/an** |
| Nouveaux humains/an          |                         **69,72 M** |
| Nouveaux humains/jour        |                       **191 013,7** |

La logique Finder retenue reste celle déjà définie dans les simulations : la récompense Finder est prélevée **à l'intérieur de la récompense PoL**, et non ajoutée au supply. 

---

# 2. Charge mondiale réelle

À maturité :

$$
69,72M/365
=
191\,013,7
$$

nouveaux humains/jour.

Avec Q=100 :

$$
191\,013,7\times100
=
\boxed{19\,101\,370}
$$

attestations/jour.

Un Finder produit effectivement :

$$
20\times24\times0,70\times0,90\times0,90
=
\boxed{272,16}
$$

attestations/jour.

Donc :

$$
F=
\frac{19\,101\,370}{272,16}
$$

$$
\boxed{F=70\,184,34}
$$

Il faut donc environ :

$$
\boxed{70\,185\ Finder\ actifs}
$$

à maturité.

Avec seulement 70 % du pool enregistré réellement disponible :

$$
\frac{70\,184,34}{0,70}
=
\boxed{100\,263,34}
$$

soit environ :

$$
\boxed{100\,264\ Finders\ enregistrés}
$$

---

# 3. Mais voici le résultat nouveau : Mode B

On applique maintenant exactement ton idée :

> **Un humain nouvellement VERIFIED peut devenir Finder.**

Chaque Finder permet :

$$
2,7216
$$

nouveaux humains/jour.

Donc si tous les humains vérifiés deviennent Finders :

$$
F(t)=H(t)
$$

et la capacité devient :

$$
C(t)=2,7216H(t).
$$

C'est une boucle auto-amplificatrice.

---

# 4. Bootstrap de 100 humains

Départ :

$$
H_0=100
$$

Capacité :

$$
100\times2,7216
=
272,16
$$

nouveaux humains/jour.

Mais la demande mondiale est :

$$
191\,013,7/jour.
$$

Le réseau commence donc avec un énorme déficit.

---

# 5. Simulation jour par jour

### Mode B — chaque VERIFIED devient Finder

| Jour | Finders/humains vérifiés | Capacité/jour | Nouveaux vérifiés |     Backlog |
| ---: | -----------------------: | ------------: | ----------------: | ----------: |
|    0 |                      100 |           272 |                 — |           0 |
|    1 |                      372 |           272 |               272 |     190 742 |
|    2 |                    1 385 |         1 013 |             1 013 |     380 742 |
|    3 |                    5 155 |         3 769 |             3 769 |     567 987 |
|    4 |                   19 183 |        14 029 |            14 029 |     744 972 |
|    5 |               **71 392** |    **52 209** |        **52 209** | **883 777** |
|    6 |                  265 692 |       194 300 |           194 300 |     880 490 |
|    7 |                  988 799 |       723 107 |           723 107 |     348 397 |
|    8 |               **1,53 M** |        2,69 M |           539 411 |       **0** |

## Résultat majeur

Le réseau **rattrape la demande mondiale au jour 8**.

Le backlog maximal est d'environ :

$$
\boxed{883\,777}
$$

humains.

Puis le réseau possède suffisamment de capacité pour absorber la demande courante.

---

# 6. Pourquoi le basculement est aussi rapide

Le mécanisme est exponentiel.

Si chaque humain vérifié devient Finder :

$$
H_{t+1}
=
H_t(1+2,7216)
$$

dans le cas idéal où la totalité de la capacité sert à vérifier de nouveaux humains.

Donc :

$$
H_{t+1}\approx3,7216H_t.
$$

C'est précisément ce qui produit :

```text
100
 ↓
372
 ↓
1 385
 ↓
5 155
 ↓
19 183
 ↓
71 392
 ↓
265 692
 ↓
988 799
 ↓
...
```

Le passage au-dessus de 70 184 Finders arrive autour du **5e jour**.

---

# 7. Mais il y a une subtilité importante

Le jour 5, le réseau possède déjà théoriquement :

$$
71\,392
$$

Finders.

C'est supérieur au besoin mondial :

$$
70\,184.
$$

Mais le réseau possède encore un backlog de :

$$
883\,777
$$

humains.

Il faut donc quelques jours supplémentaires pour absorber ce retard.

Le backlog est finalement :

$$
\boxed{0\ au\ jour\ 8}
$$

dans le modèle idéal.

---

# 8. Résultat à 365 jours

Après 365 jours, avec :

$$
191\,013,7
$$

nouveaux humains/jour :

$$
191\,013,7\times365
=
69,72M.
$$

Le réseau arrive donc à environ :

$$
\boxed{69,72M}
$$

humains vérifiés supplémentaires.

Le nombre de Finders potentiels est alors également :

$$
\boxed{\approx69,72M}
$$

**si chaque humain VERIFIED devient effectivement Finder.**

Mais — et c'est essentiel — il n'est absolument pas nécessaire que les 69,72 M soient simultanément actifs comme Finders.

La capacité théorique devient :

$$
69,72M\times272,16
$$

soit environ :

$$
\boxed{18,97\ milliards\ d'attestations/jour}.
$$

Pour une demande de seulement :

$$
19,10M/jour,
$$

la capacité devient donc **près de 1 000 fois supérieure à la demande**.

---

# 9. C'est là que le Mode B devient dangereux

Le résultat est excellent pour la capacité.

Mais il révèle immédiatement un nouveau problème :

$$
\boxed{\text{sur-capacité massive}}
$$

Après le bootstrap, si tout le monde devient Finder, le réseau n'a plus besoin de tous ces Finders.

Il faut donc **séparer :**

$$
HumanID\ VERIFIED
$$

de :

$$
Finder\ ACTIVE.
$$

Je ne recommande donc pas :

$$
F=H
$$

comme état permanent.

Je recommande :

$$
\boxed{
F_{active}(t)=\min(H(t),F_{needed}(t)+F_{reserve})
}
$$

Les autres humains restent éligibles mais ne participent pas nécessairement à chaque fenêtre.

---

# 10. Nouvelle architecture que la simulation fait apparaître

```text
                 HUMAN VERIFIED
                       │
                       ▼
                Pool Finder éligible
                       │
             sélection aléatoire
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
    Finder ACTIVE             Finder INACTIVE
          │
          ▼
  attestations HBP
          │
          ▼
   Finder Block
```

Cela permet de conserver :

* la croissance auto-amplificatrice ;
* la décentralisation ;
* une réserve énorme ;
* mais sans faire exploser inutilement la charge réseau.

---

# 11. Mode A contre Mode B

| Critère                          |             Mode A |                        Mode B |
| -------------------------------- | -----------------: | ----------------------------: |
| Bootstrap                        |          difficile | très efficace après démarrage |
| Finders nécessaires à maturité   |     ~70 185 actifs |              idem en activité |
| Finders enregistrés avec réserve |           ~100 264 |  potentiellement des millions |
| Croissance de capacité           |           linéaire |       **auto-amplificatrice** |
| Risque de sur-capacité           |             faible |                **très élevé** |
| Besoin de sélection              |              moyen |             **indispensable** |
| Résilience aux pannes            | bonne avec réserve |                    excellente |
| Complexité protocolaire          |             faible |                   plus élevée |
| Potentiel d'onboarding           |             limité |                **très élevé** |

---

# 12. Le vrai modèle que je retiendrais

Je ne choisirais finalement ni A ni B purs.

Je retiendrais :

## **Mode C — Finder pool dynamique auto-amplifié**

Les humains VERIFIED alimentent automatiquement un **pool de Finders éligibles**, mais le protocole ne sélectionne qu'un nombre nécessaire de Finders actifs.

$$
\boxed{
F_{target}
=
\left\lceil
\frac{100N_{new}}
{272,16}
\right\rceil
}
$$

Puis :

$$
\boxed{
F_{active}=F_{target}(1+\rho)
}
$$

avec, par exemple :

$$
\rho=30\%.
$$

À maturité :

$$
70\,185\times1,30
=
\boxed{91\,241}
$$

Finders actifs/réserve opérationnelle.

Le pool éligible peut être beaucoup plus grand.

---

# 13. Et la sélection doit être aléatoire

C'est fondamental pour Q=100.

Le protocole ne doit pas choisir :

```text
Finder #1
Finder #2
Finder #3
...
Finder #100
```

de façon prévisible.

Il doit sélectionner un comité de 100 parmi un pool beaucoup plus large :

$$
\boxed{
Committee_t
=
RandomSelect(100,F_{eligible})
}
$$

avec rotation.

Cela rejoint directement la logique de sécurité déjà étudiée autour de Q=100 et de l'anti-collusion.

---

# 14. Test de collusion Q=100

Sous l'hypothèse simplifiée d'une sélection indépendante uniforme, si l'attaquant contrôle une fraction \(p\) du pool :

$$
P(100/100\ compromis)=p^{100}.
$$

Quelques valeurs :

| Part malveillante |    Probabilité 100/100 |
| ----------------: | ---------------------: |
|               1 % |          \(10^{-200}\) |
|               5 % | \(7,9\times10^{-131}\) |
|              10 % |          \(10^{-100}\) |
|              25 % |  \(6,2\times10^{-61}\) |
|              50 % |  \(7,9\times10^{-31}\) |
|              90 % |  \(2,66\times10^{-5}\) |

Mais cette formule est **un modèle simplifié**, pas une preuve de sécurité du protocole. Il faudra ensuite simuler la majorité malveillante, les corrélations, les identités liées et les attaques de sélection.

---

# 15. Finder Block

Le Finder Block reste :

$$
\boxed{
R_{PoL}=R_{Miner}+R_{Finder}
}
$$

et non :

$$
R_{PoL}+R_{Finder}.
$$

Les documents montrent déjà cette logique de pool proportionnel : par exemple, avec des contributions 100/10/3, les récompenses sont distribuées proportionnellement au poids. 

Donc si :

$$
R_F=0,60
$$

et :

$$
W_A=100,\quad W_B=10,\quad W_C=3,
$$

alors :

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

La somme reste :

$$
\boxed{0,60\ ARTCB}.
$$

---

# 16. Taille du Finder Block

Je conserve également la conclusion précédente :

**ne pas dimensionner le bloc sur 8,3 milliards d'humains.**

Le document recommande une taille dynamique basée sur la demande réelle/backlog plutôt qu'une taille proportionnelle à la population. 

Donc :

$$
\boxed{
B_F(t)=
\min(B_{max},D_F(t)+M)
}
$$

où :

* \(D_F(t)\) = backlog Finder ;
* \(M\) = marge ;
* \(B_{max}\) = limite protocolaire.

À maturité, la charge moyenne théorique est :

$$
\frac{19\,101\,370}{144}
=
\boxed{132\,648,4}
$$

attestations par fenêtre de 10 minutes.

Ce nombre est une **charge moyenne**, pas une obligation de mettre 132 648 objets complets dans chaque bloc.

---

# 17. Point important découvert pendant la simulation

Le véritable goulet d'étranglement n'est donc pas :

$$
Q=100.
$$

Ce n'est même pas nécessairement :

$$
H=8,3Md.
$$

Le paramètre critique devient :

$$
\boxed{
\frac{N_{new}(t)}
{F_{active}(t)\times C_F}
}
$$

Autrement dit :

> **demande quotidienne d'attestations / capacité quotidienne réelle du pool Finder.**

C'est cette grandeur qui détermine la stabilité.

---

# 18. Condition mathématique de stabilité

Le système est stable lorsque :

$$
100N_{new}
\leq
272,16F_{active}.
$$

Donc :

$$
\boxed{
F_{active}
\geq
\frac{100N_{new}}{272,16}
}
$$

À la maturité mondiale :

$$
\boxed{
F_{active}\geq70\,185
}
$$

Si on impose 30 % de réserve :

$$
\boxed{
F_{operational}\approx91\,241
}
$$

---

# 19. Verdict de cette nouvelle simulation

### Résultat 1 — Q=100 reste viable

Je ne vois toujours pas de raison technique de réduire Q uniquement pour la capacité.

### Résultat 2 — le bootstrap est le vrai problème initial

Avec seulement 100 humains, la capacité initiale est :

$$
272,16/jour
$$

contre :

$$
191\,014/jour
$$

de demande mondiale théorique.

### Résultat 3 — le Mode B résout extrêmement vite ce problème

Si chaque VERIFIED devient éligible Finder, la capacité augmente exponentiellement.

Le backlog mondial atteint environ :

$$
\boxed{884\,000}
$$

puis tombe à :

$$
\boxed{0\ au\ jour\ 8}
$$

dans le modèle idéal.

### Résultat 4 — il ne faut surtout pas conserver F=H en permanence

Sinon la capacité devient inutilement gigantesque.

### Résultat 5 — la meilleure architecture est hybride

$$
\boxed{
HumanID_{verified}
\rightarrow FinderPool
\rightarrow RandomSelection
\rightarrow 100\ Finders
}
$$

avec un nombre de Finders actifs dimensionné dynamiquement sur le backlog.

---

## Correction de protocole à décider

Il reste une incohérence documentaire à verrouiller avant la prochaine simulation : **ton modèle utilise H₀=100**, tandis que le classeur de bootstrap recommande **101 humains Genesis**, puis Q=100 à partir du 102e. 

Je recommande de tester maintenant **le modèle hybride sur 365 jours avec sélection aléatoire de 100 Finders, réserve de 30 %, p malveillant de 1 % à 99 %, pannes, départs de Finders, backlog et rotation des comités**.
