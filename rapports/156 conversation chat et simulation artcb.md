# Rapport d’audit ARTCB — branche Cursor `tokenomics-21m-hbp-owner-decay-3fcb`

**Expertises mobilisées :** audit de code Python, architecture blockchain/consensus, tokenomics, modélisation mathématique, mécanisme d’incitation, anti-Sybil, identité matérielle/TPM, sécurité cryptographique, règlement on-chain et architecture PoL.

J’ai vérifié directement le dépôt GitHub et **la branche exacte que tu as fournie**, pas seulement `main`.

[Branche Cursor auditée — `cursor/tokenomics-21m-hbp-owner-decay-3fcb`](https://github.com/vgactech/artcb/tree/cursor/tokenomics-21m-hbp-owner-decay-3fcb?utm_source=chatgpt.com)

## 1. Certification de l’accès

L’accès GitHub fonctionne.

* Dépôt : `vgactech/artcb` → accessible.
* Branche demandée : **présente**.
* HEAD de la branche : `25b832ff911c5db03b913187124b4d239bd96239`.
* `main` reste sur `0edabb666e4014c948d5864b6377be061c50cf91`.
* Donc **les nouvelles modifications Cursor sont bien sur la branche et ne sont pas encore sur `main`**.
* Le commit est signé et GitHub le considère comme vérifié.
* Mon accès est **lecture seule** : `pull=true`, `push=false`. Je peux donc auditer, mais pas pousser moi-même une correction.

---

# 2. Ce que Cursor a effectivement réalisé

Le commit est très clair :

> `feat: tokenomics 21M coherente (R0=50, 210k) + R(H) HBP OwnerDecay`

Il annonce **535 tests passés, 20 ignorés, 0 échec**.

Et surtout, il ne s'agit pas uniquement de documentation : une nouvelle couche `src/artcb/economics/` existe réellement.

### État par fonctionnalité

| Fonction validée dans nos travaux                | État dans la branche      | Verdict                              |
| ------------------------------------------------ | ------------------------- | ------------------------------------ |
| Supply maximale 21 M                             | Implémentée               | **OK**                               |
| Reward initial 50 ARTCB                          | Implémenté                | **OK**                               |
| 210 000 blocs / epoch                            | Implémenté                | **OK**                               |
| `R(H)` décroissant avec H                        | Implémenté                | **OK avec réserve**                  |
| Pas de plancher artificiel à 1                   | Implémenté                | **OK**                               |
| HBP 10 → 60 → 20 %                               | Implémenté                | **OK**                               |
| Décroissance propriétaire par machine            | Implémentée               | **OK, à revalider mathématiquement** |
| Machine 1 = 100 % propriétaire                   | Implémenté                | **OK**                               |
| Machine 2 = humain B obligatoire                 | Implémenté                | **OK**                               |
| Machine 3 = humain C distinct                    | Implémenté                | **OK**                               |
| Réutilisation du même B interdite pour A         | Implémenté                | **OK**                               |
| Pré-blocs sans création monétaire supplémentaire | Implémenté                | **OK**                               |
| Job Provider                                     | Implémenté                | **Partiel**                          |
| Settlement A/B/HBP                               | Implémenté                | **Partiel**                          |
| API economics                                    | Implémentée               | **OK structurellement**              |
| Intégration ChainManager                         | Implémentée               | **OK structurellement**              |
| Conservation du reward                           | Testée                    | **OK**                               |
| Identité humaine réellement vérifiée             | **Non**                   | **MANQUANT**                         |
| TPM/EK comme preuve machine                      | **Non** dans cette couche | **MANQUANT**                         |
| Wallet ↔ machine cryptographiquement imposé      | **Non démontré ici**      | **MANQUANT**                         |
| Biométrie humaine                                | **Non**                   | **MANQUANT**                         |
| Finder/HBP pondéré par contribution              | **Non**                   | **CORRECTION NÉCESSAIRE**            |
| Pré-blocs réellement partitionnés par WorkID     | **Non complet**           | **CORRECTION NÉCESSAIRE**            |
| Universal Workload/bridges intégré au règlement  | **Non démontré**          | **À INTÉGRER**                       |

---

# 3. Correction majeure : les 21 M sont maintenant mathématiquement cohérents

C'était une erreur importante des anciennes versions.

Cursor a corrigé :

$$
1\times105\,000\times2=210\,000
$$

qui ne pouvait évidemment pas donner 21 M.

La branche utilise maintenant :

$$
R_0=50
$$

$$
H=210\,000
$$

donc :

$$
50\times210\,000\times2
=
\boxed{21\,000\,000}
$$

Cette identité est effectivement codée dans `tokenomics.py`.

Le test correspondant existe également.

### Mais il y a une nuance importante

Avec l'arithmétique entière en satoshi et les divisions binaires successives, le test reconnaît lui-même qu'il reste environ **0,023 ARTCB non émis**. Donc :

> **21 M est bien le hard cap, mais le calendrier discret n'atteint pas mathématiquement 21 000 000,00000000 ARTCB exactement.**

Le test accepte explicitement cette petite poussière.

Ce n'est pas une faille de sécurité, mais il faudra décider pour le protocole définitif si :

1. on accepte une supply finale légèrement inférieure à 21 M ;
2. ou si le dernier règlement doit absorber exactement le reliquat.

Je recommande **l'option 2** si « 21 000 000 exactement » reste une exigence absolue.

---

# 4. `R(H)` : Cursor a bien intégré ta décroissance démographique

La formule présente est :

$$
R(H)
=
50
\left(
\frac{\max(H,1M)}{1M}
\right)^{-\alpha}
$$

avec :

$$
\alpha=\frac{\ln(50)}{\ln(64)}
$$

Cela donne notamment :

| Humains vérifiés |     Reward théorique |
| ---------------: | -------------------: |
|              1 M |             50 ARTCB |
|             10 M |               ≈ 5,73 |
|             64 M |                  ≈ 1 |
|            100 M |              ≈ 0,657 |
|             1 Md |             ≈ 0,0753 |
|             2 Md |     encore inférieur |
|           8,3 Md | beaucoup plus faible |

Le code confirme également explicitement **« no floor at 1 ARTCB »**.

C'est conforme à ta correction précédente :

> `50 → ... → 1 → 0,99 → 0,98 → ...`

### Mais attention à une interaction nouvelle

Cursor applique :

$$
Reward_{final}
=
\min(
Reward_{schedule},
R(H),
RemainingSupply
)
$$

Donc il y a maintenant **deux mécanismes de décroissance** :

1. décroissance par calendrier de blocs ;
2. décroissance démographique `R(H)`.

Et même un troisième mécanisme :

3. **dynamic halving selon la vélocité**.

Cette troisième couche n'était pas, à mon sens, suffisamment verrouillée dans nos simulations précédentes.

---

# 5. Point que je demande de corriger : le « dynamic halving »

`tokenomics.py` ajoute :

```text
epoch_dyn = floor(log2(velocity_24h / 144))
```

avec une référence de 144 blocs/jour.

Cela signifie par exemple :

```text
144 blocs/jour   → 0 epoch supplémentaire
288 blocs/jour   → 1
1 440 blocs/jour → 3
14 400 blocs/jour → 6
```

### Problème conceptuel

Cette règle **n'était pas une composante suffisamment établie de notre modèle économique validé**.

Elle peut modifier fortement la vitesse d'émission indépendamment de H.

Donc je recommande de ne pas la considérer comme définitivement validée tant qu'elle n'a pas été :

* simulée avec `R(H)` ;
* simulée avec HBP ;
* testée sur 10/20/50/100 ans ;
* testée avec plusieurs vitesses de réseau ;
* vérifiée pour ne pas rendre la supply finale très inférieure à 21 M.

**Je classe donc ce point : ajout de Cursor à auditer, pas encore règle ARTCB définitivement validée.**

---

# 6. La décroissance du propriétaire A est bien présente

C'est l'une des modifications les plus importantes que nous avions demandées après les simulations A/B/C/D.

Cursor a créé :

`src/artcb/economics/owner_decay.py`

avec :

$$
P_{owner}(1)=100\%
$$

$$
P_{owner}(2)=50\%
$$

puis une décroissance **continue** vers :

$$
\lim_{n\rightarrow\infty}P_{owner}(n)=10\%
$$

Les points d'ancrage sont :

* n=1 → 100 %
* n=2 → 50 %
* n=1 000 → 38 %
* n=100 000 → 11,85 %
* limite → 10 %.

C'est donc bien la correction que tu réclamais précédemment :

> **la part de A diminue à chaque nouvelle machine.**

Et les tests vérifient explicitement que la courbe est strictement décroissante après la deuxième machine.

### Réserve

Nous avions étudié plusieurs formes continues dans les simulations précédentes. Cursor a choisi **une calibration particulière** avec les points 1 000 et 100 000.

Je ne la considérerais donc pas encore comme la formule mathématique définitive tant qu'on n'a pas refait une comparaison :

$$
P_{discret}
\quad vs \quad
P_{continu}
$$

sur :

$$
2,\ 3,\ 4,\ 5,\ 10,\ 100,\ 1\,000,\ 10\,000,\ 100\,000
$$

et vérifié qu'elle correspond exactement à la courbe que tu avais validée.

---

# 7. A/B/C : cette partie est correctement reprise

Le mécanisme implémenté est :

### Machine A1

```text
A
│
└── A1
    └── A = 100 %
```

### Machine A2

```text
A
│
└── A2
    ├── A ≈ 50 %
    └── B ≈ 50 %
```

### Machine A3

```text
A
│
└── A3
    ├── A < 50 %
    └── C > 50 %
```

Et surtout :

* B ne peut pas être réutilisé sur A3 ;
* C peut avoir ensuite sa propre machine C1 ;
* C peut donc simultanément être **humain lié à A3** et **propriétaire de C1**.

Ces scénarios sont explicitement testés.

C'est conforme à notre dernière simulation.

---

# 8. Très grosse lacune : « humain vérifié » n'est pas réellement vérifié

C'est probablement **la correction la plus importante à faire**.

Le code appelle :

```python
bound_human_address
```

et parle de :

```text
distinct verified human
```

Mais le registre ne fait pas réellement une preuve d'identité humaine.

Il vérifie essentiellement :

```text
B != A
B != autre B déjà utilisé
```

Le registre contient :

```text
machine_id
owner_address
machine_index
bound_human_address
device_fingerprint
```

Cela ne prouve absolument pas que B est un humain unique.

### Attaque évidente

Un utilisateur pourrait théoriquement créer :

```text
A
B1
B2
B3
B4
...
```

si rien dans le protocole extérieur ne prouve que :

$$
B_i = Human_i
$$

est une identité humaine réelle et unique.

### Ce qui manque

Il faut une vraie couche :

$$
\boxed{
HumanIdentity
}
$$

puis :

$$
\boxed{
HumanIdentity
\rightarrow Wallet
}
$$

et idéalement :

$$
\boxed{
HumanIdentity
\leftrightarrow
HardwareIdentity
\leftrightarrow
Wallet
}
$$

---

# 9. TPM : ce qui a été décidé auparavant n'est pas encore intégré ici

Nous avions établi une architecture beaucoup plus forte autour du TPM :

```text
TPM 2.0
   │
   ├── EK
   ├── EK Certificate
   └── attestation
```

Les audits précédents avaient confirmé sur la machine de test :

* TPM 2.0 fonctionnel ;
* `/dev/tpm0` ;
* `/dev/tpmrm0` ;
* certificat EK constructeur Nuvoton.

Les travaux antérieurs montrent donc que l'architecture matérielle était étudiée sérieusement.  

### Mais dans la nouvelle couche économique

`device_fingerprint` est seulement un champ optionnel.

Il n'y a pas, dans le code que j'ai audité ici, de preuve que :

$$
device\_fingerprint
=
TPM\ EK\ attested
$$

ni que la blockchain vérifie :

$$
\boxed{1\ wallet \leftrightarrow 1\ machine}
$$

au moment du règlement économique.

Donc :

**TPM/EK = encore à intégrer au protocole économique.**

---

# 10. Biométrie : oubli important

Nos travaux précédents avaient explicitement distingué :

$$
\beta:D\rightarrow W
$$

pour la liaison machine → wallet,

puis :

$$
\phi:W\rightarrow H
$$

pour la liaison wallet → humain.

Nous avions aussi constaté que **la biométrie/fingerprint n'était pas réellement intégrée dans le dépôt**.

La nouvelle branche Cursor ne corrige pas cette lacune.

Et c'est logique : il ne faut surtout pas stocker une empreinte digitale brute on-chain.

Il faudrait plutôt une architecture d'attestation d'identité où la blockchain reçoit une preuve vérifiable :

```text
Biometric / Identity Provider
            │
            ▼
      Human Credential
            │
            ▼
      Human Attestation
            │
            ▼
       ARTCB wallet
```

La donnée biométrique brute doit rester hors chaîne.

---

# 11. Pré-blocs : bonne correction, mais implémentation encore trop simplifiée

Cursor a correctement codé :

$$
\boxed{
\sum_i Reward(PB_i)=Reward_{block}
}
$$

Donc 5 pré-blocs ne produisent **pas 5 × le reward**.

Le code alloue le reward selon des poids de capacité.

Et le test vérifie précisément cette conservation.

### Mais notre règle était plus forte

Nous avions validé :

> les pré-blocs doivent être des **partitions de travail disjointes**, pas simplement des morceaux de récompense.

Il faut donc avoir :

```text
Job
 │
 ├── WorkID 001
 ├── WorkID 002
 ├── WorkID 003
 └── WorkID 004
```

avec :

$$
WorkID_i\cap WorkID_j=\varnothing
$$

pour les unités de travail exclusives.

Or ici :

```python
partition_block_reward(
    r_block_satoshi,
    worker_capacities
)
```

partitionne essentiellement **le reward selon les capacités**.

Il ne démontre pas encore :

* découpage réel du workload ;
* WorkID ;
* anti-duplication ;
* preuve de couverture ;
* preuve qu'un Worker n'a pas traité deux fois le même travail ;
* validation cryptographique de la partition.

### Verdict

**Récompense des pré-blocs : OK.**

**Partitionnement réel du travail : encore incomplet.**

---

# 12. Job Provider : la structure est là, mais pas encore le protocole complet

Cursor a bien ajouté :

```text
JobProvider
 ├── submit()
 ├── measure_capacity()
 ├── partition()
 └── mark_settled()
```

C'est une bonne base.

Mais le Job Provider conserve encore le job dans un **JSON local** et le payload est essentiellement une chaîne de caractères.

Il manque le véritable cycle :

```text
Job Provider
      ↓
Job canonicalization
      ↓
Job ID
      ↓
Work partition
      ↓
Worker
      ↓
PoL
      ↓
Validation
      ↓
Pre-block
      ↓
Final block
      ↓
Settlement
```

En particulier, il faut encore formaliser :

* hash canonique du Job ;
* version du Job ;
* WorkID ;
* preuve du résultat ;
* preuve que le résultat correspond au Job ;
* validation indépendante ;
* statut `submitted → assigned → processing → validated → settled` ;
* expiration ;
* reprise après panne ;
* double soumission ;
* résultat contradictoire.

---

# 13. Settlement : bonne architecture, mais erreur économique importante

La structure actuelle est :

$$
Reward_{block}
\rightarrow
HBP
+
WorkPool
$$

puis :

$$
WorkPool
\rightarrow
machines
\rightarrow
Owner/Human
$$

C'est correct conceptuellement.

Le code garantit même :

$$
\sum Reward_i=R_{block}
$$

### Mais HBP est actuellement distribué uniformément

Le code fait :

```text
hbp_weights = {human: 1.0 for human in humans}
```

Donc chaque humain reçoit une part égale du pool HBP.

Cela ne correspond pas complètement à la logique que nous avions étudiée autour du **Finder / contribution pondérée**.

Si nous avons :

```text
Human B → 1 contribution
Human C → 100 contributions
```

il faut décider si :

$$
Reward_B=Reward_C
$$

ou :

$$
Reward_C>Reward_B
$$

selon la contribution HBP.

**Je recommande de corriger cela avant de considérer le HBP comme définitif.**

---

# 14. Autre problème critique : la blockchain ne signe/hash pas suffisamment la partie économique

C'est une découverte importante de mon audit.

`ChainManager` construit encore le hash du bloc avec :

```text
index
timestamp
prev_hash
graph_root
merkle
pol_score
```

mais les éléments économiques ajoutés ensuite — notamment `contributors`, `block_reward`, `economics` — ne sont pas manifestement inclus dans le calcul de `block_hash` dans le code audité.

Cela signifie qu'il existe actuellement une différence entre :

> **données économiques affichées dans le bloc**

et :

> **données économiques cryptographiquement engagées par le hash du bloc.**

Pour une blockchain, c'est insuffisant.

Il faut que le hash final engage au minimum :

$$
\boxed{
Reward
+
contributors
+
machine\ bindings
+
HBP
+
settlement
+
economics
}
$$

idéalement via un `economic_root` / `settlement_root` :

```text
Block
 ├── tx_root
 ├── work_root
 ├── pol_root
 ├── economic_root   ← à ajouter
 └── state_root
```

Puis :

$$
BlockHash=
H(
Header+
txRoot+
workRoot+
economicRoot+
stateRoot
)
$$

**C'est une correction de niveau protocole, pas simplement cosmétique.**

---

# 15. Universal Workload / bridges : pas oublié dans le dépôt, mais pas relié au nouveau règlement

Nos travaux précédents avaient établi que le dépôt possède déjà une couche bridges pour différents réseaux.

Cela reste une capacité distincte.

La nouvelle branche économique n'a pas démontré que :

```text
Bitcoin
Ethereum/EVM
Solana
BNB
Polygon
Avalanche
        ↓
Universal Workload
        ↓
PoL
        ↓
Pre-blocks
        ↓
HBP / Owner / Human settlement
```

fonctionne de bout en bout.

Donc :

**Bridge = existant.**

**Universal Workload → économique ARTCB = pas encore entièrement raccordé.**

---

# 16. Ce que Cursor a ajouté qui n'était pas suffisamment demandé

Je relève surtout :

### Halving dynamique par vélocité

C'est une vraie modification du protocole économique.

Je ne la supprimerais pas nécessairement, mais je la placerais en :

> **PROPOSITION EXPÉRIMENTALE — à valider**

et non dans les règles définitives.

Pourquoi ?

Parce qu'elle interagit avec :

$$
R(H)
$$

et :

$$
21M
$$

et peut donc modifier considérablement la trajectoire d'émission.

---

# 17. Ce qui a été oublié dans notre ensemble de décisions

Voici les éléments que je recommande d'ajouter explicitement au cahier des charges avant de continuer.

## A. Identité

Il faut formaliser trois identités distinctes :

$$
\boxed{HumanID}
$$

$$
\boxed{DeviceID}
$$

$$
\boxed{WalletID}
$$

avec :

$$
HumanID\leftrightarrow WalletID
$$

$$
DeviceID\leftrightarrow WalletID
$$

mais **sans confondre les trois**.

---

## B. Preuve humaine

Il faut définir :

$$
HumanProof
$$

et son cycle :

```text
création
→ vérification
→ activation
→ renouvellement
→ révocation
→ récupération
```

Sinon le HBP reste vulnérable au Sybil.

---

## C. Preuve machine

Il faut définir :

```text
TPM EK
   +
EK Certificate
   +
attestation
   +
device binding
```

et décider ce qui se passe lorsque :

* TPM absent ;
* TPM remplacé ;
* carte mère remplacée ;
* OS réinstallé ;
* machine clonée ;
* VM ;
* cloud ;
* Replit ;
* serveur dédié.

---

## D. Ownership vs usage

Nous avons beaucoup parlé de :

> A possède la machine.

Mais il faut maintenant distinguer :

$$
Owner
$$

$$
Operator
$$

$$
HumanBound
$$

$$
JobProvider
$$

$$
Worker
$$

Ce sont potentiellement **cinq rôles différents**.

---

## E. Job Provider

Il faut décider définitivement :

> Le Job Provider reçoit-il lui-même une rémunération ?

Nos simulations avaient évolué vers l'idée que **le Job Provider est lui-même une partie productive du PoL**, et non simplement un client qui paie le Worker.

Cette règle doit maintenant être écrite dans le protocole, car le code actuel ne formalise pas encore toute cette économie.

---

## F. Finder Block

Nous avions également étudié le Finder Block / HBP.

La branche actuelle possède HBP, mais je ne vois pas encore une implémentation complète d'un :

```text
Finder Block
```

avec :

* identité du Finder ;
* contribution ;
* poids ;
* preuve ;
* anti-duplication ;
* règlement proportionnel.

Donc je considère ce point **partiellement intégré seulement**.

---

# 18. Verdict global

### Ce que je certifie comme réellement fait

**Cursor a bien réalisé une partie substantielle des modifications que nous avions validées.**

En particulier :

$$
\boxed{21M}
$$

$$
\boxed{R_0=50}
$$

$$
\boxed{210\,000\ blocs}
$$

$$
\boxed{R(H)}
$$

$$
\boxed{HBP=10\%\rightarrow60\%\rightarrow20\%}
$$

$$
\boxed{P_{owner}(n):100\%\rightarrow50\%\rightarrow10\%}
$$

$$
\boxed{A1/A2/A3+B/C}
$$

$$
\boxed{\text{pré-blocs conservatifs}}
$$

$$
\boxed{\text{Job Provider de base}}
$$

$$
\boxed{\text{settlement}}
$$

sont désormais **présents dans le code de la branche**.

---

# 19. Mais je ne certifie PAS encore « protocole ARTCB complet »

Il reste quatre niveaux de travail.

### Niveau 1 — Tokenomics

**≈ 90 %**

La base est maintenant correctement codée.

### Niveau 2 — Simulation économique

**≈ 75 %**

Les fonctions existent, mais il faut encore refaire les simulations combinées avec les paramètres réellement codés.

### Niveau 3 — Consensus blockchain

**≈ 60 %**

Le settlement est appelé par `ChainManager`, mais les données économiques doivent être **cryptographiquement engagées dans le bloc** et validées par les nœuds, pas simplement calculées localement.

### Niveau 4 — Identité humaine/matérielle

**≈ 40 %**

C'est le principal morceau manquant :

$$
TPM/EK
+
HumanProof
+
WalletBinding
+
AntiSybil
$$

doivent devenir une partie obligatoire du consensus économique.

---

# 20. Ma conclusion d'audit

**Cursor n'a pas simplement prétendu avoir fait les modifications : elles sont réellement présentes dans la branche.**

Mais il y a une distinction essentielle :

> **il a implémenté la mécanique économique comme couche applicative/protocolaire, pas encore toutes les garanties nécessaires pour en faire une règle blockchain souveraine et incontestable.**

La prochaine étape ne devrait donc **pas** être d'ajouter encore de nouvelles fonctions économiques.

Elle devrait être un **audit de verrouillage protocolaire** :

```text
                    ARTCB
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
       HumanID     DeviceID     WalletID
          │           │            │
          └───────────┼────────────┘
                      ▼
                MACHINE BINDING
                      │
                      ▼
                 JOB PROVIDER
                      │
                      ▼
              UNIVERSAL WORKLOAD
                      │
                      ▼
              DYNAMIC PRE-BLOCKS
                      │
                      ▼
                    PoL
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
     WORK REWARD                 HBP
          │                       │
          ▼                       ▼
    OwnerDecay(n)          Human contribution
          │                       │
          └───────────┬───────────┘
                      ▼
                  SETTLEMENT
                      │
                      ▼
              ECONOMIC_ROOT
                      │
                      ▼
               BLOCK HASH
                      │
                      ▼
                  CONSENSUS
```

**C'est cette dernière chaîne qui manque encore.**

Et surtout, je corrige un point de vocabulaire : **535 tests verts prouvent que l'implémentation actuelle respecte ses propres tests ; ils ne prouvent pas que toutes les décisions historiques ARTCB sont correctes ni que le protocole est sécurisé en production.** C'est précisément là que l'audit critique doit intervenir.
