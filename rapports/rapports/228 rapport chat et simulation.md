Oui. J’ai refait le contrôle **directement sur GitHub**, en repartant du dépôt réel, de l’historique des commits, du code `sync.py`, du test E2E 222 et de l’artefact JSON de mesure live. Je ne considère donc pas le rapport 222 comme une preuve suffisante à lui seul.

Il y a d’ailleurs **une correction importante** par rapport à l’audit précédent : `8a751e8…` n’est plus le `main` actuel.

# 1. État GitHub réellement actuel

Le dépôt `vgactech/artcb` est bien public, non archivé, et sa branche par défaut est `main`.

Le dernier commit que GitHub me retourne aujourd’hui est :

```text
477087c135d4c46311edecfa2bfed8cef4f505f9
```

Il a été poussé après le commit 222.

Le commit précédent important reste :

```text
8a751e8c7c7339cb945a434c8bc2eaa7749cf68b
```

C’est celui qui introduit officiellement la logique 222. Son message confirme explicitement :

* import P2P déterministe ;
* `receive` et `pull` utilisant la même décision ;
* V-01-B avec OVH1 arrêté ;
* **pas de certification Byzantine**.

### Pourquoi cette distinction est importante

C’est exactement comme une voiture :

> **Le modèle actuel peut contenir le nouveau système de freinage, mais l'essai routier que tu cites peut avoir été effectué avec la version précédente de la voiture.**

Donc :

| Élément                                 | Version    |
| --------------------------------------- | ---------- |
| `main` actuel                           | `477087c…` |
| Implémentation 222                      | `8a751e8…` |
| V-01-B live                             | `e68563e…` |
| Preuve que V-01-B utilisait le code 222 | **Non**    |

Le commit 222 lui-même documente cette distinction.

---

# 2. Ce que j'ai réellement vérifié dans le code 222

J’ai lu `src/artcb/p2p/sync.py`, pas seulement son rapport.

La fonction centrale existe réellement :

```text
decide_public_import()
```

Elle renvoie une décision structurée :

```text
reject
archive_only
append
duplicate
```

et le code impose une séquence déterministe :

```text
visibility
      ↓
structure/hash
      ↓
duplicate
      ↓
converging event
      ↓
index
      ↓
prev_hash
      ↓
append
```

Autrement dit, un nœud ne dit pas :

> « Ce bloc vient d'un autre nœud donc je lui fais confiance. »

Il dit :

> « Je prends le bloc et je passe exactement les mêmes contrôles locaux avant de décider s'il peut rejoindre ma chaîne. »

C'est une différence fondamentale.

---

# 3. Le point très important : `extend_tip` ne décide plus

Le code actuel de 222 contient :

```text
extend_tip
```

mais la valeur est explicitement ignorée dans `import_public_blocks()`.

Donc le comportement ne peut plus être :

```text
nœud A :
    extend_tip=False

nœud B :
    extend_tip=True

→ comportements différents
```

Le mécanisme devient :

```text
                    même bloc
                       │
                       ▼
             decide_public_import()
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          reject    duplicate   append
```

C'est précisément ce que le commit 222 cherchait à obtenir.

---

# 4. Et les tests ne sont pas seulement décoratifs

J’ai également lu directement `tests/test_e2e222_tip_resilience.py`.

Il teste réellement :

### G — duplicate

Le même bloc est présenté deux fois.

Résultat attendu :

```text
premier → append
second → duplicate
```

Donc pas de double ajout.

### H — mauvais `prev_hash`

Le bloc est modifié puis recalculé.

Donc ce n'est pas un simple test :

> « j'ai changé un champ et le hash ne correspond plus ».

Il vérifie également le cas où quelqu'un fabrique un bloc cohérent cryptographiquement mais qui pointe vers le mauvais précédent.

Résultat :

```text
wrong_prev_hash
```

et le tip ne bouge pas.

### I — mauvais index

Le bloc prétend être au mauvais numéro.

Le test attend :

```text
wrong_index
```

ou un rejet lié au hash.

### J — hash falsifié

Le contenu reste identique mais le hash est remplacé par :

```text
ff ff ff ... ff
```

Résultat :

```text
hash_mismatch
```

et le tip reste inchangé.

### K — événement arbitraire

C'est particulièrement intéressant.

Le test injecte :

```text
I_AM_A_MINER_NOW
```

dans `artcb_event`.

Le système ne considère pas automatiquement cet événement comme légitime.

Il produit :

```text
archive_only
not_converging_event
```

Donc :

> **« bloc public valide » ≠ « bloc autorisé à modifier le tip ».**

C'est une distinction de sécurité importante.

### M — deux producteurs

Deux chaînes partent du même état puis produisent chacune leur bloc :

```text
A → org_x
B → org_y
```

On obtient :

```text
       même bloc précédent
              │
          ┌───┴───┐
          ▼       ▼
        org_x    org_y
```

Les chaînes divergent.

Le test vérifie que le système **ne fusionne pas silencieusement les deux branches**.

---

# 5. Mais attention : M n'est PAS encore une vraie partition réseau

C'est une nuance que je veux ajouter parce qu'elle est facile à manquer.

Le test M simule :

> deux producteurs locaux ayant deux états différents.

Ce n'est pas encore :

```text
OVH1 ──────X────── OVH2
                 X
AWS3 ──────────── OVH4
```

avec une vraie coupure réseau.

### Comparaison

| Test                                     | Ce qu'il démontre                                                |
| ---------------------------------------- | ---------------------------------------------------------------- |
| M local                                  | deux chaînes concurrentes ne sont pas fusionnées silencieusement |
| vraie partition                          | comportement du réseau pendant une coupure réelle                |
| rejoin                                   | résolution après reconnexion                                     |
| partition + production                   | ce qui arrive lorsque chaque moitié produit                      |
| partition + reconnexion + nouveaux blocs | véritable test de convergence                                    |

Donc **M est utile mais insuffisant** pour certifier une partition distribuée réelle.

---

# 6. Maintenant le V-01-B live : j'ai vérifié le JSON réel

Le fichier versionné existe :

```text
rapports/evidence/222_live_20260905T134527Z.json
```

et son scénario est explicitement :

```text
V-01-B_ovh1_stopped_others_keep_tip
```

Avant l'arrêt :

```text
OVH1    tip 27350024...
OVH2    tip 27350024...
AWS3    tip 27350024...
OVH4    tip 27350024...
```

Les quatre avaient également le même :

```text
public_state_digest
```

et cinq blocs publics locaux.

Pendant l'arrêt :

```text
OVH1 → inaccessible

OVH2 → tip 27350024...
AWS3 → tip 27350024...
OVH4 → tip 27350024...
```

Les trois autres restent opérationnels et conservent leur état.

Après redémarrage :

```text
OVH1 → revient
        ↓
même tip
même digest
5 blocs
```

et le JSON indique :

```text
others_kept_tip_while_ovh1_down = true
ovh1_book_restored = true
ovh1_wiped = false
```

---

# 7. Ce que ce test prouve réellement

Il prouve quelque chose de précis et utile :

> **La disparition temporaire du nœud OVH1 ne détruit pas le livre public déjà convergé des trois autres nœuds.**

C'est une propriété de **résilience / persistance du livre**.

### Mais il ne prouve PAS :

```text
OVH1 tombe
   ↓
OVH2 devient producteur
   ↓
nouveau bloc
   ↓
AWS3 valide
OVH4 valide
   ↓
OVH1 revient
   ↓
4/4 convergent
```

Ce scénario-là n'a pas été exécuté.

Le propre rapport 222 le reconnaît.

---

# 8. Et voici une découverte importante : le transport P2P n'est pas identique

Le code est beaucoup plus intéressant ici qu'un simple résumé « receive = pull ».

### Push / receive

Le code construit une enveloppe chiffrée :

```text
ML-KEM-768
+
payload
```

puis envoie :

```text
POST /api/v1/p2p/blocks/receive
```

### Pull

Mais `pull_from_peer()` fait :

```text
GET /api/v1/p2p/blocks/public
```

puis récupère les blocs et applique localement :

```text
import_public_blocks()
```

### C'est-à-dire

Il y a deux questions différentes :

**Question A :**

> Est-ce que les deux chemins prennent la même décision sur le bloc ?

**Réponse : oui.**

**Question B :**

> Est-ce que les deux chemins ont exactement le même niveau de confidentialité pendant le transport ?

**Réponse : non, pas nécessairement.**

C'est extrêmement important.

La normalisation de la **décision d'import** est bonne.

Mais elle ne signifie pas automatiquement :

```text
receive security == pull security
```

---

# 9. Un autre point que je veux ajouter : signature ≠ hash

Le code de `verify_block_structure()` vérifie notamment la cohérence du hash.

Mais son commentaire indique également que la signature correspond à la clé du nœud émetteur et **n'est pas vérifiable localement dans cette fonction**.

Donc :

```text
Hash
```

répond à :

> « Les données correspondent-elles au hash annoncé ? »

Alors que :

```text
Signature
```

répond à :

> « Quelle identité cryptographique a autorisé/signé ce bloc ? »

Ce sont deux propriétés différentes.

### Exemple

Un attaquant peut construire :

```text
bloc parfaitement cohérent
+
hash parfaitement correct
```

mais cela ne signifie pas :

```text
bloc signé par un producteur autorisé
```

C'est pourquoi le test J ne doit pas être considéré comme un test complet d'authenticité du producteur.

---

# 10. Le problème le plus important restant

À mon avis, le prochain risque n'est plus G/H/I/J/K.

Ces cas sont maintenant raisonnablement couverts localement.

Le trou critique est :

## **Qui a effectivement le droit de produire le prochain bloc ?**

Aujourd'hui, il faut séparer :

### Validation du bloc

```text
bloc → hash correct ?
       index correct ?
       prev_hash correct ?
       événement autorisé ?
```

de :

### Autorisation de production

```text
producteur
    ↓
a-t-il le droit ?
    ↓
est-il actuellement éligible ?
    ↓
son identité est-elle valide ?
    ↓
son nœud est-il autorisé ?
    ↓
sa proposition est-elle compatible
avec le consensus ?
```

Ce deuxième niveau est beaucoup plus proche du vrai problème de **consensus de production**.

---

# 11. Tous les scénarios que je recommande maintenant

Je ne me limiterais surtout pas à G → M.

Je ferais cette matrice :

| ID | Scénario                                       | État                 |
| -- | ---------------------------------------------- | -------------------- |
| G  | bloc dupliqué                                  | **testé**            |
| H  | mauvais `prev_hash`                            | **testé localement** |
| I  | mauvais index                                  | **testé localement** |
| J  | hash falsifié                                  | **testé localement** |
| K  | événement arbitraire                           | **testé localement** |
| M  | deux producteurs / fork local                  | **testé localement** |
| N  | vraie partition réseau                         | **à tester**         |
| O  | reconnexion après partition                    | **à tester**         |
| P  | producteur principal hors ligne                | **à tester**         |
| Q  | producteur secondaire prend la relève          | **à tester**         |
| R  | deux producteurs produisent simultanément      | **à tester**         |
| S  | producteur revient après avoir été absent      | **à tester**         |
| T  | nœud revient avec chaîne ancienne              | **à tester**         |
| U  | nœud revient avec chaîne falsifiée             | **à tester**         |
| V  | replay d'un ancien bloc valide                 | **à tester**         |
| W  | même bloc envoyé par plusieurs pairs           | **à tester**         |
| X  | pair malveillant envoie beaucoup de blocs      | **à tester**         |
| Y  | pair autorisé mais clé compromise              | **à tester**         |
| Z  | partition + production des deux côtés + rejoin | **à tester**         |

Et j'ajouterais encore :

### AA — rollback

Le nœud redémarre avec un état disque plus ancien.

```text
hauteur 100
   ↓ crash
retour hauteur 97
```

Que fait-il ?

### AB — corruption disque

Un fichier de blocs est partiellement corrompu.

### AC — horloge incorrecte

Un nœud possède une horloge fortement décalée.

### AD — spam

Un pair envoie 100 000 blocs invalides.

### AE — replay

Un ancien bloc parfaitement valide est présenté comme nouveau.

### AF — split-brain

Deux ensembles de nœuds pensent chacun être le groupe canonique.

C'est un scénario extrêmement important.

---

# 12. Et surtout : le cas « créateur mort »

Il faut maintenant aller plus loin que V-01-B.

Il y a une énorme différence entre :

### Cas 1 — créateur mort mais aucun nouveau bloc

```text
OVH1 OFF
  ↓
OVH2/3/4
  ↓
ne font rien
  ↓
ancien état conservé
```

C'est **ce que V-01-B démontre**.

### Cas 2 — créateur mort et réseau continue

```text
OVH1 OFF
   ↓
OVH2 produit
   ↓
AWS3 valide
   ↓
OVH4 valide
   ↓
nouveau tip
```

C'est **celui qu'il faut maintenant démontrer**.

### Cas 3 — créateur revient

```text
OVH1 OFF
   ↓
bloc 6 produit
   ↓
OVH1 revient avec bloc 5
   ↓
synchronisation
   ↓
bloc 6 récupéré
```

Et il faut vérifier que le nœud ne fait surtout pas :

```text
bloc 6
   ↓
écrasé
   ↓
retour au bloc 5
```

---

# 13. Attention également au mot « BFT »

C'est probablement le point le plus important conceptuellement.

Dans les spécifications précédentes, on avait :

```text
N = 4
F = 1
Q = 2F + 1 = 3
```

Cela signifie qu'avec quatre participants, trois peuvent constituer un quorum dans le modèle BFT considéré.

Mais :

> **un quorum BFT de règlement n'est pas automatiquement un mécanisme BFT de création de blocs.**

C'est-à-dire :

```text
Settlement BFT
      ≠
Block production consensus
```

Le code 222 ne doit donc pas être déclaré :

> « Byzantine safe »

simplement parce que trois nœuds sur quatre sont encore actifs.

Le commit 222 le dit lui-même explicitement : **pas de certification Byzantine**.

---

# 14. Nouvelle situation de certification

Après ma vérification, je classerais l'état ainsi :

| Domaine                                 | Verdict                                |
| --------------------------------------- | -------------------------------------- |
| dépôt GitHub                            | **OK**                                 |
| `main` actuel identifié                 | **OK — `477087c…`**                    |
| logique `decide_public_import()`        | **OK inspectée**                       |
| receive/pull → même décision            | **OK inspecté**                        |
| G                                       | **PASS local**                         |
| H                                       | **PASS local**                         |
| I                                       | **PASS local**                         |
| J                                       | **PASS local**                         |
| K                                       | **PASS local**                         |
| M                                       | **PASS local**                         |
| V-01-B keep-book                        | **PASS live rapporté + artefact JSON** |
| V-01-B avec code 222 réellement déployé | **NON démontré**                       |
| producteur de remplacement              | **NON démontré**                       |
| partition réseau réelle                 | **NON démontrée**                      |
| rejoin réel                             | **NON démontré**                       |
| fork distribué réel                     | **NON démontré**                       |
| Byzantine                               | **NON certifié**                       |
| signature producteur complète           | **à approfondir**                      |
| confidentialité receive/pull identique  | **NON**                                |
| consensus canonique de production       | **NON suffisamment démontré**          |

---

# 15. Une dernière chose nouvelle dans le `main`

Le `main` vient encore d'avancer après 222 avec le commit `477087c…`.

Ce commit ajoute notamment une configuration MCP/Doppler et un rapport d'installation machine locale. Le rapport annonce :

```text
804 PASS
30 FAIL
9 SKIP
843 exécutés
96,4 %
```

Mais **je ne transformerais surtout pas “96,4 %” en “96,4 % du protocole certifié”**.

Pourquoi ?

Parce que les 30 échecs sont justement classés par catégories :

* liboqs absent ;
* tests HTTP ;
* certification distribuée ;
* SSL ;
* Replit ;
* API non démarrée ;
* timing machine.

Donc un taux global de tests verts mélange des tests unitaires, environnementaux, locaux et distribués.

**C'est un peu comme dire qu'un avion est certifié parce que 96,4 % de toutes les cases d'une checklist sont cochées : il faut regarder quelles cases sont rouges.**

Le rapport lui-même montre d'ailleurs que les tests de certification distribuée ne sont pas simplement assimilables à des tests locaux.

---

# 16. Mon verdict critique

**Le travail 222 est réel et techniquement utile.** Ce n'est pas seulement un rapport généré : j'ai retrouvé la fonction dans le code et les tests qui l'appellent.

Mais il faut maintenant arrêter de considérer :

```text
G H I J K M + V-01-B
```

comme la fin de la validation.

Cela nous amène au véritable prochain niveau :

```text
                    ARTCB
                      │
        ┌─────────────┴─────────────┐
        │                           │
  validation bloc              consensus
        │                           │
   hash/index/prev             qui produit ?
   duplicate/event             qui autorise ?
        │                       qui tranche ?
        │                           │
        └─────────────┬─────────────┘
                      │
              réseau réellement
                distribué
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      panne        partition    Byzantine
          │           │           │
          ▼           ▼           ▼
       reprise      rejoin      quorum
```

**C'est cette deuxième moitié qui déterminera si ARTCB possède réellement un consensus distribué robuste, et pas seulement un mécanisme correct d'import de blocs.**

Et je retiens surtout ceci pour la suite : **je ne présenterai plus un test “live” comme preuve du code courant lorsque le SHA du test est différent du SHA actuellement déployé.** Ici, le JSON est parfaitement utile comme preuve historique, mais il faut le qualifier comme tel.
