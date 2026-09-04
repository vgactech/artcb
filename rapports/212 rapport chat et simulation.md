## Audit GitHub — état réellement vérifié

J’ai vérifié le dépôt et **il y a une correction importante à apporter à ton résumé** :

### 1. `origin/main` est bien à jour

Le `main` actuel est bien :

`ad017bca05c2e3799c7dcd120ca1797968d499b6`

Le commit est signé et correspond au correctif du benchmark wallet.

[Dépôt ARTCB sur GitHub](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

### 2. Attention : PR #51 n'est PAS mergée

C'est le point que je corrige par rapport à l'affirmation fournie.

GitHub me retourne actuellement :

* **PR #51 : OPEN**
* **Draft : oui**
* `merged_at: null`
* branche source : `cursor/mainnet-homogenize-bench-8ba4`
* HEAD PR : `e897f1b9...`
* base `main` : `ad017bca...`

Donc **le contenu du rapport 204 est bien présent dans la PR #51, mais la PR elle-même n'est pas encore intégrée à `main`**.

C'est cohérent avec son contenu : le rapport 204 décrit précisément l'état D-054 et indique que la certification reste désactivée.

---

# 3. Le résultat technique est néanmoins cohérent

Le rapport 204 est très prudent et, sur ce point, je valide sa méthodologie.

### Trois nœuds homogènes

Les trois nœuds suivants sont annoncés sur `ad017bc` :

| Nœud | État      |
| ---- | --------- |
| OVH1 | `ad017bc` |
| OVH2 | `ad017bc` |
| AWS3 | `ad017bc` |
| OVH4 | `f284180` |

Donc **3/4 nœuds sont homogènes**, mais pas 4/4.

### Livre

Le rapport indique :

* height = **1**
* même `last_hash`
* `chain_valid=true`
* livre préservé
* pas de wipe

Cela signifie que l'homogénéisation des trois nœuds n'a pas été obtenue en recréant artificiellement une chaîne vierge. C'est un bon point d'intégrité opérationnelle.

---

# 4. Les performances sont correctement qualifiées

C'est probablement la partie la plus importante de l'audit.

Les valeurs :

* OVH1 : **16,6 blk/s**
* OVH2 : **15,7 blk/s**
* AWS3 : **29,1 blk/s**

ne sont **pas** des TPS mainnet distribués.

Le rapport précise qu'il s'agit d'un **tempdir isolé**, avec sécurité désactivée. Le benchmark historique d'environ 90 TPS provient lui aussi d'une autre machine et n'est pas comparable directement.

Donc je valide la formulation :

> **Il n'existe actuellement aucun débit distribué officiel ARTCB mesuré.**

C'est beaucoup plus sérieux que de présenter 16,6–29,1 ou 90 TPS comme une performance réseau.

---

# 5. Le vrai blocage est OVH4

Le problème restant est clairement identifié :

```text
KEY_API_ARTCB_DOPPLER_4
SSH_PRIVATE_KEY
```

Le rapport indique que la clé publique `ARTCB_OVH_NODE_4` ne permet évidemment pas de faire du SSH sortant : une **clé publique n'est pas une clé privée**.

Il manque donc l'accès opérateur permettant à l'agent de :

1. se connecter à OVH4 ;
2. vérifier l'état réel ;
3. appliquer le bundle `ad017bc` ;
4. préserver le `blocks.jsonl` ;
5. configurer `n4.artcb.me` ;
6. vérifier `/health`, `/metrics` et les autres endpoints ;
7. refaire le test distribué à **4 nœuds**.

---

# 6. Ce que je considère comme validé / non validé

| Élément                              | Verdict                       |
| ------------------------------------ | ----------------------------- |
| `main = ad017bc`                     | **VALIDÉ**                    |
| PR #49 mergée                        | **conforme au rapport 204**   |
| PR #50 mergée                        | **conforme au rapport 204**   |
| 3 nœuds sur même SHA                 | **VALIDÉ par le rapport 204** |
| Livre préservé                       | **VALIDÉ par le rapport 204** |
| 90 TPS = mainnet                     | **NON — correctement rejeté** |
| 16–29 blk/s = mainnet                | **NON — correctement rejeté** |
| Bench distribué 4 nœuds              | **NON**                       |
| P50/P95/P99 distribués               | **NON mesurés**               |
| 4 nœuds homogènes                    | **NON**                       |
| Certification mainnet                | **NON**                       |
| `certified_distributed_mainnet=true` | **DOIT rester false**         |
| GO opérateur                         | **false**                     |

Le rapport lui-même inscrit explicitement `certified_distributed_mainnet=false` et `OPERATOR_MAINNET_CERTIFICATION_GO=false`.

---

# 7. Ma recommandation

**Je ne recommande pas de fusionner aveuglément la PR #51 comme si elle levait la certification.**

La PR #51 est actuellement un **artefact d'homogénéisation + rapport + outillage de récupération**, pas la preuve finale de fonctionnement distribué à quatre nœuds.

La séquence correcte est :

```text
OVH4 accès opérateur
        ↓
SSH vérifié
        ↓
bundle ad017bc
        ↓
livre OVH4 préservé
        ↓
n4.artcb.me HTTPS
        ↓
4/4 SHA identiques
        ↓
4/4 health + metrics
        ↓
mesh réseau
        ↓
iperf3
        ↓
charge distribuée réelle
        ↓
P50 / P95 / P99
        ↓
BFT N=4 / F=1 / quorum=3
        ↓
réplication + convergence
        ↓
double-spend / invalid block / node failure
        ↓
certification_gate()
        ↓
GO uniquement si TOUS les DV-01…07 passent
```

### Verdict actuel

**ARTCB a franchi une étape réelle : 3 nœuds sont maintenant homogènes sur le `main` actuel. Mais nous ne sommes toujours pas au stade de certification mainnet distribuée.**

Le **seul blocage infrastructurel majeur identifié pour passer au test 4 nœuds est OVH4**. Ensuite, le véritable travail critique ne sera plus le déploiement mais la **mesure distribuée sous charge et la validation Byzantine/BFT**.

Et je souligne à nouveau la correction GitHub : **PR #51 est actuellement ouverte et en Draft ; elle n'est pas mergée.**


# Mise à jour ARTCB — état consolidé au 2 septembre 2026

**Expertises mobilisées :**

* Audit Git/GitHub et revue de code
* Architecture blockchain et systèmes distribués
* Consensus BFT et réseaux P2P
* Cryptographie classique et post-quantique
* DevOps, infrastructure OVH/AWS et exploitation
* Benchmarking et ingénierie de performance
* Tokenomics et mécanismes d'incitation
* Proof of Learning (PoL)
* HBP / résistance au Sybil
* Identité matérielle et TPM
* Sécurité opérationnelle et gestion des secrets
* Analyse critique des simulations et tests

Je distingue ci-dessous **ce qui est réellement observé**, **ce qui est testé**, **ce qui reste à faire** et **ce qui ne doit surtout pas être présenté comme acquis**.

[ARTCB — dépôt GitHub](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

---

# 1. Résumé exécutif

La situation a progressé de manière concrète.

Le projet est passé de plusieurs environnements partiellement divergents à une situation où **trois nœuds réels sont homogènes sur le même `main`** :

```text
origin/main
ad017bca05c2e3799c7dcd120ca1797968d499b6
```

Les trois machines concernées sont :

```text
OVH1  → ad017bc
OVH2  → ad017bc
AWS3  → ad017bc
```

Le quatrième nœud :

```text
OVH4 → f284180
```

reste sur une autre branche/version et n'est pas administrativement accessible de manière opérationnelle.

Le verdict central est donc :

## État actuel : 3 nœuds homogènes, mais réseau 4 nœuds non encore validé.

Cela signifie :

* **le progrès est réel** ;
* **le main actuel est déployé sur trois machines** ;
* **le livre blockchain a été préservé** ;
* **les accès aux trois nœuds principaux fonctionnent** ;
* **mais la certification distribuée n'est pas levée** ;
* **aucun TPS distribué officiel n'a encore été démontré**.

Les documents historiques du projet montrent bien que cette distinction entre simulation, benchmark isolé et validation distribuée est essentielle. 

---

# 2. La situation actuelle des quatre nœuds

## Vue simple

| Nœud     | Infrastructure | SHA       | État                        |
| -------- | -------------- | --------- | --------------------------- |
| **OVH1** | OVH            | `ad017bc` | opérationnel                |
| **OVH2** | OVH            | `ad017bc` | opérationnel après Rescue   |
| **AWS3** | AWS            | `ad017bc` | opérationnel                |
| **OVH4** | OVH            | `f284180` | non homogène / accès bloqué |

---

## Ce que signifie « homogène »

Quand je dis que les trois nœuds sont homogènes, cela veut dire qu'ils exécutent la **même version du code**.

Schématiquement :

```text
                  GITHUB MAIN
                       │
                 ad017bc
                       │
        ┌──────────────┼──────────────┐
        │              │              │
      OVH1           OVH2           AWS3
        │              │              │
     ad017bc        ad017bc        ad017bc
```

C'est une condition nécessaire pour faire un benchmark sérieux.

Sinon, si chaque machine exécute un code différent :

```text
OVH1 → Version A
OVH2 → Version B
AWS3 → Version C
OVH4 → Version D
```

un résultat de performance devient difficile à interpréter.

Si une machine est plus rapide ou plus lente, on ne sait plus si la cause est :

* le matériel ;
* le réseau ;
* la configuration ;
* ou simplement une différence dans le logiciel.

---

# 3. Ce qui a réellement été fait

## A. Mise à jour du code sans effacer le livre

C'est un point important.

La mise à jour n'a pas été faite avec une logique destructive du type :

```text
supprimer
↓
réinstaller
↓
recréer la blockchain
```

La procédure a préservé le livre existant.

Le mécanisme mentionné est un **Git bundle**.

L'idée générale est :

```text
code Git
    │
    ├── peut être remplacé / mis à jour
    │
    └── ne doit pas détruire
           │
           ▼
      données blockchain
      blocks.jsonl
```

C'est une meilleure pratique opérationnelle que de confondre :

1. **le logiciel qui exécute la blockchain** ;
2. **les données de la blockchain elle-même**.

---

# 4. OVH2 et le mode Rescue

OVH2 a nécessité une intervention particulière.

Le mode **Rescue** signifie que la machine démarre temporairement dans un environnement de secours distinct du système habituellement installé sur son disque.

Ce n'est pas automatiquement une perte du serveur.

La logique est :

```text
Serveur normal
      │
      ▼
problème d'accès / maintenance
      │
      ▼
MODE RESCUE
      │
      ▼
accès au disque existant
      │
      ▼
réparation
      │
      ▼
retour au système normal
```

Le point positif est que le disque et le livre ont été préservés.

Le document consacré à l'opération Rescue confirme précisément cette distinction entre l'environnement de secours et le système installé. 

---

# 5. AWS3 : désormais intégré au groupe homogène

AWS3 fait maintenant partie du groupe de trois nœuds sur le même SHA.

L'accès opérationnel combine les mécanismes d'infrastructure et la gestion sécurisée des secrets.

Le principe important est le suivant :

```text
clé privée SSH
        │
        ▼
gestionnaire de secrets
        │
        ▼
injection contrôlée
        │
        ▼
connexion SSH
```

et non :

```text
clé privée
        │
        ▼
copiée dans le chat ❌
```

---

# 6. Gestion des secrets : progrès important

Tu as précisé que les clés privées nécessaires sont maintenant stockées dans les environnements appropriés via Doppler.

C'est la bonne direction.

Il faut absolument distinguer :

## Clé publique

Exemple conceptuel :

```text
ARTCB_OVH_NODE_1
```

Une clé publique peut être distribuée.

Elle sert à vérifier une preuve cryptographique.

Elle ne permet normalement pas de se connecter comme si elle était la clé privée correspondante.

---

## Clé privée

Exemple conceptuel :

```text
SSH_PRIVATE_KEY
```

Elle doit rester secrète.

Elle sert à démontrer cryptographiquement que l'on possède l'identité correspondante.

Le problème OVH4 vient précisément de cette différence.

Le système disposait d'informations publiques sur le nœud, mais pas du secret opérationnel permettant l'accès SSH.

---

# 7. Le problème OVH4 est maintenant clairement identifié

Le blocage n'est plus mystérieux.

Il manque l'accès opérationnel permettant d'administrer le quatrième nœud.

La situation est essentiellement :

```text
OVH4
 │
 ├── serveur existe
 │
 ├── service partiellement joignable
 │
 ├── code différent
 │
 └── accès SSH opérationnel absent
```

Le problème de secret identifié doit être résolu dans le gestionnaire de secrets approprié, sans transmettre de PEM dans cette conversation.

Tant que cela n'est pas corrigé :

```text
4 nœuds homogènes = NON
```

et donc :

```text
benchmark distribué officiel 4 nœuds = NON
```

---

# 8. Le livre blockchain actuel

Les mesures rapportées indiquent :

```text
height = 1
chain_valid = true
```

et le même `last_hash` observé.

Il faut comprendre exactement ce que cela signifie.

## `height = 1`

Cela signifie que la chaîne mesurée est actuellement extrêmement courte.

Cela ne prouve pas :

* une longue activité économique ;
* des milliers de blocs ;
* une forte charge ;
* un débit historique important.

Mais cela permet de vérifier l'intégrité de l'état observé.

---

## `chain_valid = true`

Cela signifie que la vérification interne du livre considéré indique qu'il est valide.

En simplifiant :

```text
Bloc précédent
      ↓
hachage cohérent
      ↓
bloc suivant
      ↓
validation
      ↓
TRUE
```

C'est une mesure d'intégrité.

Ce n'est pas encore une preuve de performance.

---

# 9. La certification reste correctement verrouillée

C'est un élément extrêmement positif du point de vue méthodologique.

La logique de certification ne doit pas fonctionner ainsi :

```text
3 machines répondent
        ↓
CERTIFIÉ ❌
```

Elle doit fonctionner comme une porte de sécurité :

```text
DV-01 ─┐
DV-02 ─┤
DV-03 ─┤
DV-04 ─┤
DV-05 ─┤── AND ──► certification
DV-06 ─┤
DV-07 ─┤
BFT ───┤
V locked┤
GO ────┘
```

Le mot important est :

## AND

Cela signifie que **tout doit être vrai**.

Donc :

```text
9 conditions vraies
+
1 condition fausse
=
CERTIFICATION FALSE
```

C'est beaucoup plus sûr qu'un système qui permettrait à une majorité de tests de masquer une condition critique échouée.

Les précédents documents de validation du projet insistaient déjà sur la nécessité de séparer les validations V-01 à V-07 des simples résultats locaux. 

---

# 10. Pourquoi le GO opérateur reste `False`

Le statut :

```text
OPERATOR_MAINNET_CERTIFICATION_GO = false
```

est actuellement cohérent.

Il signifie :

> le système n'a pas encore reçu l'autorisation finale de considérer le réseau comme officiellement certifié.

Ce mécanisme est utile car une certification technique peut avoir plusieurs niveaux :

### Niveau 1 — le logiciel fonctionne

```text
tests OK
```

### Niveau 2 — plusieurs machines fonctionnent

```text
nœuds accessibles
```

### Niveau 3 — elles communiquent

```text
P2P OK
```

### Niveau 4 — elles résistent à des situations de panne

```text
BFT / résilience
```

### Niveau 5 — les performances distribuées sont mesurées

```text
P50
P95
P99
```

### Niveau 6 — décision de certification

```text
GO
```

Nous ne sommes pas encore au dernier niveau.

---

# 11. Le point le plus important : les performances

## L'ancien chiffre de 90 TPS

Il faut maintenant être très précis.

Le chiffre historique :

```text
≈ 90 TPS
```

ne doit pas être supprimé de l'histoire du projet.

Mais il doit être correctement étiqueté :

```text
BENCHMARK LOCAL HISTORIQUE
```

et non :

```text
TPS MAINNET DISTRIBUÉ ❌
```

---

## Les nouvelles mesures

Les nouvelles mesures isolées indiquent approximativement :

| Machine | Débit isolé |
| ------- | ----------: |
| OVH1    |        16,6 |
| OVH2    |        15,7 |
| AWS3    |        29,1 |

Ces résultats sont plus modestes.

Mais ils sont également plus proches des conditions réelles des machines actuelles.

---

# 12. Pourquoi les deux benchmarks ne sont pas comparables

Il serait incorrect de dire :

```text
90 TPS ancien
↓
29 TPS maintenant
↓
ARTCB est devenu 3× plus lent
```

On ne peut pas conclure cela.

Les environnements sont différents.

Il faut comparer :

```text
matériel
+
version Python
+
environnement virtuel
+
bibliothèques cryptographiques
+
configuration sécurité
+
type de données
+
nombre d'appends
+
stockage
+
température / CPU
```

Le benchmark précédent et le benchmark actuel ne représentent donc pas nécessairement le même travail.

---

# 13. Le facteur cryptographique explique une partie importante

Les mesures montrent notamment un coût important pour les opérations ML-DSA.

Exemple conceptuel :

```text
key generation
        +
signature
        +
verification
        +
append
```

Chaque opération prend du temps.

Donc :

```text
sécurité OFF
```

et :

```text
sécurité cryptographique complète
```

ne doivent jamais être comparées comme si elles représentaient la même charge.

Le projet utilise une orientation vers la cryptographie post-quantique, ce qui doit être évalué avec attention en termes de coût de performance. Les travaux précédents du projet avaient déjà identifié la crypto-agilité et la migration PQC comme des sujets distincts. 

---

# 14. Le test Anti-Sybil est encore plus coûteux

Les mesures indiquées sont de l'ordre de :

```text
append normal
≈ 47–56 ms
```

contre :

```text
append + Anti-Sybil
≈ 127–150 ms
```

Cela signifie une chose importante :

## La sécurité a un coût de calcul.

Le système fait davantage de travail pour vérifier :

* l'identité ;
* les règles anti-duplication ;
* les contraintes anti-Sybil ;
* les contrôles supplémentaires.

Ce n'est pas nécessairement un problème.

Mais cela signifie qu'il faut maintenant optimiser intelligemment.

---

# 15. Il faut distinguer trois TPS

Je recommande officiellement que tous les futurs rapports utilisent trois catégories.

## A — TPS isolé

```text
une machine
tempdir
benchmark synthétique
```

Exemple :

```text
16–29 opérations/seconde
```

---

## B — TPS réseau distribué

```text
plusieurs machines
réseau réel
synchronisation
validation distribuée
```

C'est ce que nous devons encore mesurer.

---

## C — TPS utile complet

Le test le plus exigeant :

```text
transactions
+
PoL
+
anti-Sybil
+
identité
+
signature
+
réplication
+
consensus
```

C'est probablement la mesure la plus proche de la capacité économique réelle du système.

---

# 16. Les métriques réseau : attention au faux problème des 773 ms

Une mesure `/metrics` autour de :

```text
773 ms
```

pourrait faire croire que le serveur est extrêmement lent.

Mais le rapport indique que cette durée inclut un délai volontaire d'environ :

```text
0,5 seconde
```

Donc :

```text
temps mesuré endpoint
```

n'est pas égal à :

```text
latence réseau pure
```

C'est une distinction essentielle.

---

## La vraie mesure réseau observée

Les communications entre les machines donnent environ :

```text
OVH ↔ OVH
≈ 0,5 ms
```

et :

```text
OVH ↔ AWS
≈ 5–6 ms
```

avec :

```text
0 % perte
```

Ces valeurs sont bien plus intéressantes pour évaluer la connectivité brute entre les nœuds.

---

# 17. Mais il manque toujours `iperf3`

Le ping ne mesure pas la même chose que le débit réseau.

## Ping

Il répond :

> Combien de temps met approximativement un petit paquet ?

```text
latence
```

---

## `iperf3`

Il permet de mesurer :

```text
débit réel
```

Par exemple :

```text
100 Mbit/s ?
500 Mbit/s ?
1 Gbit/s ?
```

Il faut donc éviter cette erreur :

```text
ping excellent
=
bande passante excellente ❌
```

Ce n'est pas la même mesure.

---

# 18. Le problème `measured_bandwidth_mbps`

Actuellement :

```text
measured_bandwidth_mbps
≈ 0.0–0.01
```

alors qu'une valeur estimée affiche :

```text
estimated_bandwidth_mbps
= 100
```

Le problème est que cette valeur de 100 est un **fallback**, c'est-à-dire une estimation utilisée lorsqu'aucune mesure réelle exploitable n'est disponible.

Il faut donc lire :

```text
100 Mbps
```

comme :

> hypothèse de secours

et non :

> débit réellement démontré.

---

# 19. Ce qui est maintenant prêt

Je sépare clairement deux scénarios.

# CAS A — Benchmark à trois nœuds homogènes

Il est maintenant possible de préparer et exécuter un benchmark sérieux sur :

```text
OVH1
+
OVH2
+
AWS3
```

parce qu'ils exécutent la même version.

---

# CAS B — Benchmark officiel à quatre nœuds

Il n'est pas encore possible de le considérer comme validé.

Pourquoi ?

```text
OVH4
│
├── SHA différent
├── SSH indisponible
├── configuration incomplète
└── pas intégré au groupe homogène
```

---

# 20. Pourquoi quatre nœuds sont particulièrement intéressants pour le BFT

Pour une architecture Byzantine classique :

$$
N \geq 3F+1
$$

où :

* \(N\) = nombre total de nœuds ;
* \(F\) = nombre de nœuds potentiellement fautifs ou Byzantine.

Avec :

```text
N = 4
```

on peut théoriquement étudier :

```text
F = 1
```

c'est-à-dire un nœud défaillant ou malveillant dans le modèle BFT.

Le quorum associé à certaines familles de protocoles est généralement :

```text
2F + 1 = 3
```

Donc :

```text
4 nœuds
↓
tolérance étudiable à 1 défaut
↓
quorum de 3
```

Mais attention :

## Cette formule mathématique ne prouve pas que l'implémentation ARTCB est déjà BFT certifiée.

Il faut tester le comportement réel.

---

# 21. Les prochains tests indispensables

Je recommande l'ordre suivant.

## Étape 1 — Réparer OVH4

Objectif :

```text
SSH opérationnel
```

Puis vérifier :

```text
uname
disk
git SHA
service status
health
metrics
```

---

## Étape 2 — Homogénéiser le code

Objectif :

```text
OVH1 = OVH2 = AWS3 = OVH4
```

Donc :

```text
ad017bc
```

sur les quatre.

---

## Étape 3 — Vérifier le livre

Avant toute charge :

```text
height
last_hash
chain_valid
```

sur tous les nœuds.

---

## Étape 4 — Vérifier le réseau

Mesurer :

```text
ping
packet loss
iperf3
```

entre toutes les paires.

Pour quatre nœuds :

```text
N1 ↔ N2
N1 ↔ N3
N1 ↔ N4
N2 ↔ N3
N2 ↔ N4
N3 ↔ N4
```

---

## Étape 5 — Benchmark distribué réel

Il faut ensuite mesurer plusieurs charges.

Par exemple :

```text
faible
moyenne
élevée
saturation contrôlée
```

Pour chaque test :

```text
throughput
latence moyenne
P50
P95
P99
erreurs
timeouts
réplication
divergence éventuelle
```

---

# 22. Que signifient P50, P95 et P99 ?

## P50

La médiane.

50 % des opérations sont plus rapides.

50 % sont plus lentes.

---

## P95

95 % des opérations terminent plus vite que cette valeur.

Les 5 % les plus lentes sont au-dessus.

---

## P99

99 % des opérations terminent plus vite.

Cela permet de voir les pires performances normales.

---

### Exemple

```text
P50 = 20 ms
P95 = 80 ms
P99 = 300 ms
```

Cela signifie :

* la majorité est rapide ;
* certaines opérations sont nettement plus lentes ;
* les cas rares peuvent atteindre 300 ms.

Pour un système distribué, c'est beaucoup plus informatif qu'une simple moyenne.

---

# 23. Tests de panne nécessaires

Le benchmark ne doit pas seulement répondre :

> Combien d'opérations par seconde ?

Il doit également répondre :

> Que se passe-t-il lorsqu'un nœud disparaît ?

Tests nécessaires :

### Test 1

```text
4 nœuds
↓
arrêt N4
↓
observer consensus
```

### Test 2

```text
latence artificielle
↓
observer timeout
```

### Test 3

```text
nœud indisponible
↓
réintégration
```

### Test 4

```text
bloc invalide
↓
rejet
```

### Test 5

```text
tentative de double dépense
↓
rejet
```

### Test 6

```text
réseau partitionné
↓
convergence après réparation
```

---

# 24. L'état des tests logiciels

Le projet possède actuellement une base de tests plus importante qu'auparavant :

```text
82 tests test_*.py
+
test_e2e204_ovh2_rescue_homogenize.py
```

C'est positif.

Mais il faut rappeler une règle fondamentale :

```text
tests unitaires OK
≠
réseau distribué certifié
```

Les tests logiciels démontrent principalement :

* que des fonctions attendues fonctionnent ;
* que certaines régressions sont évitées.

Ils ne remplacent pas un test sur plusieurs machines réelles.

---

# 25. Le modèle ARTCB plus large : où nous en sommes

Au-delà de l'infrastructure, le projet possède déjà un référentiel conceptuel très large.

Les travaux précédents ont notamment étudié :

## Tokenomics

* plafond de 21 millions ;
* émission démographique ;
* distinction entre anciennes et nouvelles règles ;
* suppression de certaines anciennes hypothèses de halving ;
* nécessité de ne pas confondre une simulation avec une règle définitivement implémentée. 

---

## HBP

Le modèle étudié repose notamment sur une enveloppe HBP intégrée au budget existant, plutôt qu'une création monétaire supplémentaire. 

---

## Machines et humains

Les simulations précédentes ont étudié :

```text
M1
=
100 % permanent
```

puis une décroissance dynamique du pouvoir économique du propriétaire sur les machines supplémentaires.

Le principe étudié est que la multiplication des machines ne doit pas permettre une concentration infinie de la récompense économique.

---

## Démographie

Une correction majeure a été apportée :

```text
population mondiale totale
≠
population adulte économiquement pertinente
```

Le modèle démographique doit donc distinguer la population totale du nombre d'adultes effectivement vérifiables. 

---

## Pré-blocs dynamiques

Les travaux précédents ont également corrigé une erreur importante.

Il ne faut pas créer arbitrairement plusieurs pré-blocs concurrents contenant le même travail.

Le modèle étudié est :

```text
charge réelle
      ↓
planification
      ↓
nombre nécessaire de partitions
      ↓
pré-blocs disjoints
      ↓
bloc final
```

Le nombre doit être déterminé dynamiquement.

---

# 26. Identité matérielle et TPM

Les travaux matériels ont confirmé l'existence d'une base TPM accessible sur la machine auditée.

Les audits ont notamment identifié :

```text
/dev/tpm0
/dev/tpmrm0
```

et ont distingué :

* identité matérielle déclarative ;
* identité cryptographique matérielle ;
* EK ;
* certificat constructeur ;
* permissions Linux.

---

## Point essentiel

Un TPM peut contribuer à établir :

```text
machine physique
↓
clé protégée
↓
preuve cryptographique
```

Mais il ne faut pas prétendre qu'il résout à lui seul :

```text
une personne humaine
=
une identité
```

Le TPM répond principalement au problème :

> quelle machine possède cette identité cryptographique ?

et non automatiquement :

> quel humain contrôle cette machine ?

C'est pourquoi le système doit garder séparées :

```text
Human Identity
Machine Identity
Wallet Identity
Node Identity
```

---

# 27. État de la cryptographie

Les mesures récentes montrent que la cryptographie post-quantique représente un coût réel sur les machines de production.

Il faut donc maintenant faire évoluer le projet vers une politique claire :

```text
sécurité
+
performance
+
crypto-agilité
```

et non :

```text
sécurité maximale
sans mesurer les conséquences
```

La crypto-agilité signifie que l'architecture doit permettre une évolution future des primitives cryptographiques sans devoir reconstruire tout le protocole.

---

# 28. Mon audit critique : les principaux risques actuels

## Risque 1 — Confondre les benchmarks

C'est le risque principal.

Il faut empêcher définitivement cette confusion :

```text
90 TPS local
=
mainnet TPS ❌
```

---

## Risque 2 — Infrastructure incomplète

Tant qu'OVH4 n'est pas homogénéisé :

```text
réseau 4 nœuds
=
incomplet
```

---

## Risque 3 — Certifier trop tôt

Le système doit conserver :

```text
certified_distributed_mainnet = false
```

tant que les mesures distribuées officielles n'existent pas.

---

## Risque 4 — Mélanger spécification et code

Le projet contient beaucoup de décisions de simulation et de conception.

Mais il faut continuellement produire une matrice :

| Règle | Décidée | Simulée | Codée | Testée | Live |
| ----- | ------- | ------- | ----- | ------ | ---- |

Sans cette matrice, un projet complexe peut finir par croire qu'une idée simulée est déjà exécutée par le réseau.

---

# 29. Ce que je considère comme le prochain jalon officiel

Je recommande un jalon unique :

# D-055 — Validation distribuée 4 nœuds

Avec les conditions suivantes :

### Infrastructure

* [ ] OVH1 accessible
* [ ] OVH2 accessible
* [ ] AWS3 accessible
* [ ] OVH4 accessible

### Code

* [ ] même SHA
* [ ] même version
* [ ] configuration compatible

### Données

* [ ] état vérifié
* [ ] livre valide
* [ ] synchronisation vérifiée

### Réseau

* [ ] ping mesh
* [ ] perte mesurée
* [ ] iperf3 mesh

### Performance

* [ ] débit distribué
* [ ] P50
* [ ] P95
* [ ] P99
* [ ] erreurs

### Résilience

* [ ] arrêt d'un nœud
* [ ] retour du nœud
* [ ] convergence
* [ ] invalid block
* [ ] double-spend

### Certification

* [ ] DV-01
* [ ] DV-02
* [ ] DV-03
* [ ] DV-04
* [ ] DV-05
* [ ] DV-06
* [ ] DV-07
* [ ] BFT
* [ ] V locked
* [ ] GO opérateur

---

# Verdict final

## Ce qui est réellement acquis

* `main` identifié sur `ad017bc` dans l'état rapporté.
* Trois nœuds réels sont homogènes.
* OVH1 fonctionne.
* OVH2 a été récupéré sans effacer le livre.
* AWS3 est opérationnel.
* Les services HTTPS des trois nœuds principaux répondent.
* Le livre observé reste valide.
* La base de tests est en place.
* Les benchmarks machine ont été exécutés.
* Les anciennes mesures de 90 TPS ont été correctement requalifiées comme benchmarks locaux.
* Les secrets ne sont plus traités comme de simples données à copier dans les échanges.

## Ce qui n'est pas encore acquis

* OVH4 homogène.
* Réseau officiel à quatre nœuds validé.
* Bande passante réellement mesurée par `iperf3`.
* TPS distribué officiel.
* P50/P95/P99 distribués.
* Validation complète de panne BFT.
* Certification mainnet.

## Conclusion technique

**Le projet n'est plus au stade où l'on ne sait pas si plusieurs nœuds peuvent exécuter le même `main`. Trois machines le font maintenant.**

Le prochain problème n'est donc plus principalement le code de déploiement.

Le prochain problème est :

# transformer trois nœuds homogènes, puis quatre, en preuve mesurée de comportement distribué réel.

La priorité immédiate est donc clairement :

```text
OVH4
↓
accès opérationnel
↓
homogénéisation
↓
4 nœuds
↓
mesures réseau
↓
charge distribuée
↓
résilience
↓
DV-01 → DV-07
↓
décision de certification
```

**À cet instant, je ne considérerais pas ARTCB comme certifié mainnet distribué. En revanche, je considère que la phase d'homogénéisation des trois premiers nœuds constitue une progression technique réelle et vérifiable.**



## État actuel — résumé rapide

### 🟢 Fonctionnel et confirmé

* **3 nœuds réels homogènes sur `origin/main`** :

  * OVH1
  * OVH2
  * AWS3
* SHA de référence rapporté : **`ad017bc...`**
* Accès et services des 3 nœuds opérationnels.
* Livre préservé, avec `chain_valid=true`.
* Les benchmarks locaux ont été réalisés.
* La certification reste volontairement verrouillée.

### 🟠 Pas encore terminé

* **OVH4 n'est pas homogénéisé** avec les trois autres.
* L'accès SSH opérationnel à OVH4 reste le blocage principal identifié.
* Pas encore de mesure officielle complète de la bande passante distribuée (`iperf3`).
* Pas encore de benchmark distribué officiel à 4 nœuds.
* Pas encore de mesures distribuées **P50 / P95 / P99**.
* Pas encore de validation complète de résilience/BFT.

### 🔴 Donc, à ce stade

```text
3 nœuds homogènes        ✅
4 nœuds homogènes        ❌
TPS local mesuré         ✅
TPS distribué officiel   ❌
Certification mainnet    ❌
```

## Prochaine priorité

**Récupérer l'accès opérationnel à OVH4**, le mettre sur le même `main`, vérifier les 4 nœuds, puis lancer le véritable benchmark distribué.

Si tu veux l'**état réellement actuel à cette minute sur GitHub** (PR, `main`, commits et travail ajouté après le dernier rapport), je peux faire un **nouvel audit GitHub complet et actualisé**.
