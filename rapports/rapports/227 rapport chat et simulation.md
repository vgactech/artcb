Oui. J’ai repris **directement `vgactech/artcb` sur GitHub**, en séparant le code actuel, les tests, les commits et l’artefact de mesure live. Je ne vais pas considérer le rapport 222 comme une preuve indépendante lorsqu’il existe une possibilité de vérifier la même affirmation dans le code.

[Dépôt ARTCB — GitHub](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

## 1. Premier constat : le SHA actuel est bien `8a751e8…`

Le dernier commit de `main` est actuellement :

`8a751e8c7c7339cb945a434c8bc2eaa7749cf68b`

Son message indique explicitement :

* import P2P déterministe ;
* `receive` et `pull` utilisant la même décision ;
* V-01-B réalisé avec OVH1 arrêté ;
* **pas de certification Byzantine**.

Donc sur ce point, le texte que tu as fourni est **cohérent avec GitHub**.

Mais il y a une nuance extrêmement importante :

> **Le live V-01-B a été exécuté avec `e68563e…`, avant le commit `8a751e8…`.**

Le JSON live le confirme : les quatre nœuds mesurés pendant le test avaient `git_sha = e68563e8…`.

C'est-à-dire que :

```text
e68563e
   │
   ├── test live V-01-B
   │      └── OVH1 arrêté
   │
   └── ensuite
          ↓
       8a751e8
          └── nouvelle logique decide_public_import()
```

**Donc il serait incorrect de dire que V-01-B a validé la nouvelle logique 222.**

C'est le premier point que je verrouillerais dans la documentation.

---

# 2. Ce que le code 222 fait réellement

J’ai lu `src/artcb/p2p/sync.py` sur le `main` actuel.

La nouvelle fonction est bien :

```text
decide_public_import()
```

et elle retourne une décision structurée :

```text
reject
archive_only
append
duplicate
```

La logique est effectivement commune au traitement des blocs reçus et tirés.

Le point important est ici :

```text
visibility
   ↓
structure/hash
   ↓
duplicate
   ↓
converging event
   ↓
symbols liés
   ↓
index
   ↓
prev_hash
   ↓
append
```

Cela constitue une **machine de décision déterministe** : pour un même bloc et le même état local, le nœud doit arriver au même verdict.

### C'est-à-dire quoi ?

Avant, un paramètre externe pouvait influencer le comportement :

```text
receive
   → extend_tip=False

pull
   → autre comportement
```

Maintenant :

```text
receive ─┐
         ├──> decide_public_import()
pull ────┘
```

C'est beaucoup plus propre.

La fonction accepte encore `extend_tip`, mais le code actuel le fait volontairement :

```text
_ = extend_tip
```

Donc le paramètre historique n'a plus d'autorité.

**C'est une bonne correction architecturale.**

---

# 3. Les protections G/H/I/J/K/M sont réellement testées

J’ai également lu le test `tests/test_e2e222_tip_resilience.py`.

Il ne se contente pas de tester « le code ne plante pas ». Il teste plusieurs attaques ou états incohérents.

| Scénario     | Ce qui est injecté                               | Résultat attendu          | État |
| ------------ | ------------------------------------------------ | ------------------------- | ---- |
| **G**        | même bloc deux fois                              | `duplicate`               | PASS |
| **H**        | mauvais `prev_hash` mais hash recalculé          | rejet                     | PASS |
| **I**        | mauvais index                                    | rejet                     | PASS |
| **J**        | hash falsifié                                    | `hash_mismatch`           | PASS |
| **K**        | événement arbitraire                             | `archive_only`            | PASS |
| **M**        | deux producteurs créent des branches différentes | pas de fusion silencieuse | PASS |
| Receive/Pull | même bloc                                        | même décision             | PASS |

Les tests sont donc plus intéressants qu'un simple test unitaire.

Par exemple, H est particulièrement utile :

```text
attaquant modifie prev_hash
        ↓
recalcule correctement le hash
        ↓
le hash du bloc est donc mathématiquement valide
        ↓
mais prev_hash ne correspond pas au tip local
        ↓
REJECT
```

**C'est-à-dire que l'attaquant ne peut pas simplement recalculer le SHA pour rendre une chaîne incohérente acceptable.**

---

# 4. Mais j'ai trouvé une nuance importante que je ne laisserais pas passer

Le commentaire du code dit :

> « receive and pull must call this same function »

Et effectivement, **l'import final utilise la même fonction**.

Mais le **transport** n'est pas identique.

### Receive

Le chemin receive passe par une enveloppe chiffrée.

Le code récupère :

```text
decrypt_envelope()
      ↓
blocks
      ↓
import_public_blocks()
      ↓
decide_public_import()
```

### Pull

Le chemin pull fait actuellement :

```text
GET /api/v1/p2p/blocks/public
      ↓
blocks
      ↓
import_public_blocks()
      ↓
decide_public_import()
```

Le commentaire du code indique même explicitement :

> `GET clair pour liste, puis import local`

Donc :

### Verdict

**Même décision de sécurité d'import : OUI.**

**Même protection de transport : NON.**

C'est une distinction fondamentale.

C'est-à-dire :

```text
                    ┌─ receive → transport chiffré
P2P                 │
                    └─ pull    → GET de liste en clair
                              ↓
                       même décision d'import
```

La convergence de décision est donc améliorée, mais **cela ne signifie pas que les deux chemins ont le même niveau de confidentialité réseau**.

---

# 5. Autre point critique : le B-live ne teste PAS la production

C'est probablement le point le plus important pour la prochaine étape.

Le test réel du 5 septembre a fait :

```text
État initial

OVH1 ─────────────┐
OVH2 ─────────────┤
AWS3 ─────────────┤── même livre
OVH4 ─────────────┘
       5 blocs
       même tip
```

Puis :

```text
STOP OVH1

OVH1       X

OVH2       5 blocs
AWS3       5 blocs
OVH4       5 blocs
           même tip
```

Puis :

```text
START OVH1

OVH1       5 blocs
OVH2       5 blocs
AWS3       5 blocs
OVH4       5 blocs
           même tip
```

Le JSON contient :

* `others_kept_tip_while_ovh1_down=true`
* `ovh1_book_restored=true`
* `ovh1_wiped=false`
* même `last_hash`
* même `public_state_digest`
* 5 blocs sur les quatre nœuds.

### Donc ce test démontre :

**la disparition temporaire d'OVH1 ne détruit pas le livre déjà convergé.**

C'est une propriété de **résilience de stockage/continuité de lecture**.

---

# 6. Ce qu'il ne démontre PAS

Il ne démontre pas :

```text
OVH1 disparaît
      ↓
OVH2 devient producteur
      ↓
création d'une nouvelle ORG
      ↓
nouveau bloc
      ↓
AWS3 accepte
      ↓
OVH4 accepte
      ↓
OVH1 revient
      ↓
OVH1 récupère le nouveau bloc
      ↓
4/4 convergent
```

Ça serait beaucoup plus puissant.

C'est le véritable scénario :

## **V-01-B producteur**

Et c'est justement celui qu'il faut maintenant faire.

Le rapport/commit 222 reconnaît lui-même qu'aucune nouvelle ORG n'a été créée pendant l'arrêt d'OVH1.

---

# 7. Pourquoi le scénario M local ne suffit pas

Le test M est utile :

```text
A :
Genesis
  ↓
ORG-X

B :
Genesis
  ↓
ORG-Y
```

Les deux tips divergent.

Le test vérifie ensuite que A ne fusionne pas silencieusement la chaîne B.

C'est bon.

Mais ce test est **local**.

C'est-à-dire :

```text
simulation Python
       ≠
4 serveurs Internet réellement indépendants
```

Une simulation peut démontrer que la fonction respecte une règle.

Elle ne démontre pas que :

* les délais réseau réels ;
* les retries ;
* les connexions concurrentes ;
* les timeouts ;
* les partitions ;
* les redémarrages ;
* les états persistants ;
* les authentifications ;
* les différentes horloges ;
* les services systemd ;
* les chemins P2P

se comportent correctement ensemble.

---

# 8. Et il reste un problème encore plus profond : `append_block` n'est toujours pas BFT

J'ai vérifié `consensus_spec.py`.

Le fichier dit explicitement :

```text
N >= 3F+1
Q = 2F+1
```

avec :

```text
N = 4
F = 1
Q = 3
```

pour le moteur BFT de **prepare/commit**.

Mais il précise également :

```text
not_block_append_bft = True
```

et :

```text
canonical_tip_sim = longest valid chain
```

Donc il faut absolument éviter cette confusion :

### BFT Settlement

```text
prepare
   ↓
commit
   ↓
3/4 quorum
```

### Append blockchain

```text
candidate block
   ↓
validation
   ↓
chain selection
   ↓
append
```

Le premier existe.

Le second **n'est pas encore un consensus BFT complet**.

---

# 9. Ce que je considère maintenant comme réellement validé

Je séparerais l'état en **4 niveaux de preuve**.

| Niveau                                           | Preuve                   | Verdict                 |
| ------------------------------------------------ | ------------------------ | ----------------------- |
| **Code**                                         | `decide_public_import()` | **PASS**                |
| **Tests locaux**                                 | T-E48, 17 tests          | **PASS**                |
| **Live historique**                              | V-01-B avec OVH1 arrêté  | **PASS pour keep-book** |
| **Live avec nouveau bloc produit pendant panne** | OVH2/3/4 produisent      | **NON TESTÉ**           |

Et surtout :

> **Le live historique n'a pas tourné avec `8a751e8`.**

Donc je ne mettrais surtout pas une coche :

```text
V-01-B = certified
```

Je mettrais :

```text
V-01-B — keep-book : PASS
V-01-B — producer failover : PENDING
V-01-B — code 222 live : PENDING
```

---

# 10. Scénarios supplémentaires que tu n'avais pas explicitement mentionnés

C'est ici que je recommande d'élargir l'audit.

## A — Producteur mort

```text
OVH1 OFF
OVH2 crée ORG
AWS3 reçoit
OVH4 reçoit
OVH1 revient
```

**Priorité maximale.**

---

## B — Producteur mort + deux producteurs concurrents

```text
OVH1 OFF

OVH2 → ORG-A
AWS3 → ORG-B
OVH4 → observe
```

Question :

> Le réseau choisit-il une chaîne déterministe ou peut-il conserver deux histoires incompatibles ?

C'est plus difficile que M local.

---

## C — Partition réseau

```text
OVH1 ─ OVH2

       X

AWS3 ─ OVH4
```

Chaque moitié continue à fonctionner.

Puis :

```text
réseau rétabli
       ↓
rejoin
       ↓
résolution
```

C'est **le test que je considère aujourd'hui comme le vrai verrou critique**.

Le rapport 222 reconnaît que partition/rejoin n'est pas démontré en live.

---

## D — Réseau partitionné + création d'ORG

Encore plus intéressant :

```text
A/B :
ORG-X

C/D :
ORG-Y
```

Puis réunion.

Ce test permet de savoir si le protocole possède réellement une règle de résolution de fork ou s'il ne fait que refuser l'import adverse.

---

## E — Replay

Un attaquant capture :

```text
bloc valide N
```

puis le renvoie :

```text
N
N
N
N
N
```

Le système doit rester :

```text
1 append
+
duplicates
```

et jamais :

```text
5 append
```

Le test G vérifie déjà la version locale de ce comportement.

---

## F — Bloc valide mais événement non autorisé

Très important avec ARTCB :

```text
hash correct
prev_hash correct
index correct
visibility=public
```

mais :

```text
artcb_event = événement arbitraire
```

Le système doit dire :

```text
archive_only
```

et non :

```text
append
```

C'est exactement la raison pour laquelle K est intéressant.

---

# 11. Mon verdict global après cette vérification

### 🟢 Correct

* dépôt `main` vérifié ;
* `8a751e8` réellement présent ;
* décision d'import centralisée ;
* receive/pull utilisent la même décision ;
* validation hash ;
* duplicate protection ;
* `prev_hash` ;
* index ;
* événements convergents ;
* tests G/H/I/J/K/M ;
* preuve live que les trois autres nœuds conservent le livre quand OVH1 tombe ;
* restauration d'OVH1 sans wipe.

### 🟠 Partiel

* code 222 **pas encore démontré en live** ;
* pull et receive ont la même décision mais pas le même transport ;
* BFT settlement existe mais n'est pas le consensus de `append_block` ;
* fork local testé mais pas fork réel distribué ;
* production pendant panne non testée.

### 🔴 Non démontré

* partition réelle + rejoin ;
* deux producteurs live simultanés ;
* producteur mort puis production par les survivants ;
* résolution déterministe d'un fork réel ;
* Byzantine général ;
* certification complète du réseau.

---

# 12. Le prochain audit que je recommande

Je ne passerais **pas** directement à V-02.

Je ferais :

```text
V-01-B.1
Producteur OVH1 OFF
        ↓
OVH2 produit
        ↓
AWS3 + OVH4 convergent
        ↓
OVH1 revient
        ↓
4/4 même tip
```

Puis immédiatement :

```text
V-01-B.2
Partition 2 + 2
        ↓
production des deux côtés
        ↓
reconnexion
        ↓
détection du fork
        ↓
règle déterministe
        ↓
4/4 même état
```

Puis :

```text
V-01-B.3
même scénario
+
code SHA 8a751e8
+
preuve cryptographique
+
logs bruts
+
état avant/pendant/après
```

**C'est cette séquence qui permettra de passer d'une démonstration “le livre survit à la panne” à une démonstration “le protocole continue à produire et converge après panne”.**

Et je recommande que chaque prochain live publie **les logs bruts et les hashes des logs**, pas seulement un rapport Markdown. Le rapport est l'explication ; le log brut est la matière première de l'audit. C'est une différence importante entre **preuve reproductible** et **affirmation documentée**.

Enfin, le `main` est bien public et non archivé, mais la connexion GitHub dont je dispose ici est **lecture seule** : je peux vérifier et analyser le dépôt, pas prétendre avoir exécuté moi-même une commande SSH sur les quatre serveurs. Le live V-01-B ci-dessus est donc une **preuve versionnée produite par le système**, que j'ai pu contrôler contre le code et l'artefact GitHub, et non une nouvelle sonde réseau indépendante de ma part.
