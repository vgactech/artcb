# Simulation ARTCB suivante — audit du dépôt + simulation de référence

J’ai effectué l’audit du dépôt **avant** de lancer la simulation, comme demandé.

[Dépôt GitHub ARTCB — `vgactech/artcb`](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

## 1. Expertises mobilisées

* **Audit de code Python / architecture logicielle**
* **Architecture blockchain et consensus PoL**
* **Tokenomics / émission monétaire**
* **Mechanism design et théorie des incitations**
* **Anti-Sybil / identité humaine**
* **Identité matérielle TPM / wallet-machine**
* **Scheduling et pré-blocs dynamiques**
* **Comptabilité des récompenses**
* **Modélisation économique A/B**
* **Simulation numérique**

---

# 2. Première conclusion : le dépôt est accessible

L'accès à `vgactech/artcb` est confirmé, avec la branche `main` lisible. Mes permissions actuelles sont **lecture uniquement** : `pull=true`, `push=false`.

J'ai notamment vérifié directement :

* `src/artcb/chain/manager.py`
* `src/artcb/tokenomics.py`
* `src/artcb/bridges/manager.py`
* les modules/tests wallet et hardware identity
* les rapports de rewards/minage.

---

# 3. Découverte critique : le code actuel et le modèle ARTCB validé ne sont PAS encore identiques

C'est le point le plus important de cette simulation.

### Le code actuel indique :

```text
INITIAL_BLOCK_REWARD_ARTCB = 1
HALVING_INTERVAL = 105 000 blocs
MAX_SUPPLY = 21 000 000
```

Le fichier `tokenomics.py` confirme explicitement ces trois paramètres.

Et `ChainManager` applique réellement le halving à partir de ces constantes.

### Conséquence mathématique

Avec :

$$
R_0=1
$$

et :

$$
210\,000/2=105\,000
$$

on obtient asymptotiquement :

$$
1\times105000\times2
=
\boxed{210\,000\ ARTCB}
$$

et **pas 21 millions**.

C'est donc une incohérence réelle entre le code actuel et le plafond annoncé.

---

# 4. J'ai donc lancé deux simulations séparées

Pour ne pas masquer cette contradiction, je distingue :

### Simulation A — comportement réel du dépôt actuel

$$
R_0=1
$$

$$
H=105\,000
$$

### Simulation B — modèle ARTCB que nous avons validé dans les simulations précédentes

$$
R_0=50
$$

$$
H=210\,000
$$

ce qui donne :

$$
50\times210000\times2
=
\boxed{21\,000\,000}
$$

Cette deuxième version est mathématiquement cohérente avec le plafond de 21 M.

---

# 5. Résultat — code actuellement présent

Avec un bloc de référence de 600 s :

$$
52\,596\ blocs/an
$$

|   Temps |     Blocs | Supply cumulée avec le code actuel |
| ------: | --------: | ---------------------------------: |
|    1 an |    52 596 |                       52 596 ARTCB |
|   2 ans |   105 192 |                            105 096 |
|   5 ans |   262 980 |                            170 745 |
|  10 ans |   525 960 |                          203 467,5 |
|  20 ans | 1 051 920 |                          209 796,8 |
|  50 ans | 2 629 800 |                          ≈ 210 000 |
| 100 ans | 5 259 600 |                      ≈ **210 000** |

### Verdict

**Le code actuel ne peut pas distribuer 21 M avec ces paramètres.**

Le hard cap de 21 M existe, mais la trajectoire d'émission actuelle converge vers environ :

$$
\boxed{210\,000}
$$

avant d'atteindre le plafond.

---

# 6. Simulation suivante — modèle validé ARTCB

Je reprends maintenant le modèle que nous avions validé pour les simulations économiques :

$$
R_0=50
$$

$$
E_{tranche}=210\,000\ blocs
$$

$$
R_n=50\times2^{-n}
$$

Donc :

| Epoch | Reward/bloc | Émission de l'epoch |         Cumul |
| ----: | ----------: | ------------------: | ------------: |
|     0 |          50 |          10 500 000 |    10 500 000 |
|     1 |          25 |           5 250 000 |    15 750 000 |
|     2 |        12,5 |           2 625 000 |    18 375 000 |
|     3 |        6,25 |           1 312 500 |    19 687 500 |
|     4 |       3,125 |             656 250 |    20 343 750 |
|     5 |      1,5625 |             328 125 |    20 671 875 |
|     6 |     0,78125 |           164 062,5 |  20 835 937,5 |
|     7 |    0,390625 |           82 031,25 | 20 917 968,75 |
|   ... |         ... |                 ... |    → **21 M** |

C'est cette structure qui est cohérente avec :

$$
\boxed{S_{max}=21\,000\,000}
$$

---

# 7. Résultat temporel de cette version

Avec 600 s/bloc :

| Horizon | Supply cumulée |
| ------: | -------------: |
|    1 an |   **2,6298 M** |
|   5 ans |  **11,8245 M** |
|  10 ans |  **17,0745 M** |
|  20 ans | **20,34675 M** |
|  50 ans |  **20,9962 M** |
| 100 ans |     **≈ 21 M** |
| 200 ans |     **≈ 21 M** |

Donc la supply est pratiquement entièrement distribuée sur plusieurs décennies, sans dépasser :

$$
\boxed{21M}
$$

---

# 8. Maintenant la simulation transactionnelle A/B/C/D

Je conserve la règle que nous avions validée :

> **Une nouvelle machine du même propriétaire entraîne une diminution progressive de la part économique du propriétaire.**

Donc :

| Machine contrôlée par A |            Part propriétaire |
| ----------------------: | ---------------------------: |
|                      A1 | 100 % de l'enveloppe machine |
|                      A2 |                         50 % |
|                      A3 |                         40 % |
|                      A4 |                         30 % |
|                      A5 |                         20 % |
|                     A6+ |                         10 % |

Le complément revient à l'humain indépendant lié à cette machine.

Ainsi :

$$
A_2=A(50\%)+B(50\%)
$$

$$
A_3=A(40\%)+C(60\%)
$$

et non :

$$
A_3=A(50\%)+C(50\%)
$$

Cette décroissance est donc bien **indépendante de la courbe HBP**.

---

# 9. Bloc simulé

Je prends un scénario :

```text
Humains vérifiés : 100 M
Reward global : 50 ARTCB
Machines : 4

A possède :
  A1
  A2 → B obligatoire
  A3 → C obligatoire

D possède :
  D1
```

À 100 M humains, avec la fonction HBP validée précédemment :

$$
P_{HBP}\approx11,2048\%
$$

Donc :

$$
Reward_{HBP}
=
50\times0,112048
$$

$$
\boxed{5,6024\ ARTCB}
$$

Il reste pour le travail des machines :

$$
50-5,6024
=
\boxed{44,3976\ ARTCB}
$$

Avec quatre machines :

$$
44,3976/4
=
11,0994\ ARTCB
$$

par unité de production dans cette simulation.

---

# 10. Paiement exact du bloc

### Machine A1

A possède entièrement A1 :

$$
A=11,0994
$$

### Machine A2

$$
50/50
$$

Donc :

$$
A=5,5497
$$

$$
B=5,5497
$$

### Machine A3

$$
40/60
$$

Donc :

$$
A=4,4398
$$

$$
C=6,6596
$$

### Machine D1

$$
D=11,0994
$$

---

# 11. HBP

Les quatre humains vérifiés :

$$
A,B,C,D
$$

reçoivent ici, à titre de scénario d'équilibrage :

$$
5,6024/4
=
1,4006
$$

chacun.

### Total final

| Humain    | Production machine |    HBP |   **Total** |
| --------- | -----------------: | -----: | ----------: |
| **A**     |            21,0889 | 1,4006 | **22,4895** |
| **B**     |             5,5497 | 1,4006 |  **6,9503** |
| **C**     |             6,6596 | 1,4006 |  **8,0602** |
| **D**     |            11,0994 | 1,4006 | **12,5000** |
| **TOTAL** |            44,3976 | 5,6024 | **50,0000** |

**Aucune création monétaire supplémentaire.**

$$
\boxed{\sum Rewards=50}
$$

---

# 12. Ce que le dépôt sait déjà faire

Le système actuel possède déjà une vraie mécanique de contributeurs :

```text
contributors[]
      ↓
PoL score de chaque contributeur
      ↓
PolScorer.split_reward()
      ↓
reward_satoshi individuel
```

`ChainManager.append_block()` calcule actuellement les récompenses à partir des scores PoL des contributeurs.

Le dépôt possède également un mécanisme Anti-Sybil appliqué aux contributeurs avant l'acceptation du bloc.

Donc le **moteur comptable de base existe**.

Ce qui n'est pas encore démontré comme implémentation complète dans le code actuel est notre couche :

$$
\boxed{
Machine\ Count
\rightarrow Owner\ Decay
\rightarrow Human\ Binding
\rightarrow HBP
\rightarrow Settlement
}
$$

---

# 13. Autre élément déjà réellement présent : Universal Workload

Le dépôt actuel possède une couche bridges qui prend en charge :

$$
Bitcoin
$$

$$
Ethereum
$$

$$
Solana
$$

$$
BNB
$$

$$
Polygon
$$

$$
Avalanche
$$

et transforme les transactions importées en `ir_text` exploitable par le pipeline PoL.

C'est important pour la simulation : le concept de **travail universel** n'est donc plus seulement théorique.

---

# 14. Résultat critique de cette simulation

Il y a maintenant **trois niveaux clairement séparés**.

### Niveau 1 — déjà dans le dépôt

```text
Wallet
PoL
contributors
Reward splitting
Anti-Sybil
TPM/hardware identity
Bridges
Transactions
```

### Niveau 2 — déjà défini dans nos simulations

```text
21 M hard cap
50 ARTCB initial
décroissance A → 50/40/30/20/10 %
Human B obligatoire
HBP dynamique
pré-blocs dynamiques disjoints
Job Provider
paiement automatique B
```

### Niveau 3 — encore à intégrer au protocole réel

```text
MachineCount → OwnerDecay
HumanBinding
HBP settlement
Dynamic PreBlock Scheduler
Job Provider accounting
21M-consistent emission
```

---

# 15. Correction que je considère désormais indispensable

Je ne certifie **pas** que le dépôt actuel implémente déjà notre tokenomics finale.

Au contraire, l'audit vient de démontrer une divergence précise :

$$
\boxed{
Code actuel:
1\ ARTCB + 105k\ blocs
\Rightarrow 210k\ ARTCB
}
$$

contre :

$$
\boxed{
Modèle validé:
50\ ARTCB + 210k\ blocs
\Rightarrow 21M\ ARTCB
}
$$

C'est une différence suffisamment importante pour **ne pas la masquer dans les prochaines simulations**.

Et le code possède en plus un **halving dynamique basé sur la vitesse des blocs**, qui peut accélérer encore la réduction du reward lorsque la vitesse dépasse 144 blocs/jour.

### Conclusion de la simulation suivante

Le modèle économique que nous avions construit est **mathématiquement cohérent**, mais **il n'est pas encore identique au code `main` actuel**.

La prochaine simulation doit donc partir de cette base corrigée :

$$
\boxed{
21M
+
50\ ARTCB
+
210\,000\ blocs/epoch
+
OwnerDecay
+
HumanBinding
+
HBP
+
Dynamic\ PreBlocks
+
JobProvider
}
$$

et **ne plus mélanger cette simulation avec le `tokenomics.py` actuel** tant que la divergence n'est pas résolue.
