Oui. Je viens de me remettre à jour **directement sur GitHub**, et l’état a changé depuis les anciens audits.

[Dépôt GitHub ARTCB — `vgactech/artcb`](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

## État actuel vérifié — 4 septembre 2026

### 1. Dépôt

Le dépôt `vgactech/artcb` est :

* **public** ;
* **non archivé** ;
* branche par défaut : **`main`** ;
* accessible en lecture depuis GitHub.

Mon accès GitHub actuel est **lecture seule** : je peux auditer, comparer et analyser, mais je n'ai pas actuellement les permissions `push/admin/maintain`.

### 2. Activité récente

Les derniers commits montrent une activité importante entre le 2 et le 3 septembre :

| Date    | Élément                                   | État                      |
| ------- | ----------------------------------------- | ------------------------- |
| 2 sept. | preuve live `main` suivie par les 4 nœuds | présent dans l'historique |
| 2 sept. | WebAuthn / biométrie                      | intégré                   |
| 2 sept. | validation D-056 après DV-02/DV-06        | intégré                   |
| 2 sept. | interface `/register` biométrique         | intégré                   |
| 2 sept. | correction du bouton Visage/caméra        | intégré                   |
| 3 sept. | plusieurs déploiements Replit             | nouveaux commits présents |
| 3 sept. | dernier commit observé                    | `addc6e9e…`               |

Le commit `12b95841…` est particulièrement important : son message indique que **DV-02 et DV-06 ont été mesurés PASS sur les 4 nœuds**, avec flood `64×4 = 200`, `locks 401`, `SSRF 400`, et restauration du netem OVH4. Le mécanisme de certification a alors été positionné après ces validations.

### 3. Le README actuel est lui-même beaucoup plus avancé

Le `main` annonce actuellement :

* **519/519 tests** ;
* **520 blocs actifs** ;
* ML-DSA-65 + Ed25519 ;
* PoL basé sur `Δ compression + validation sémantique` ;
* architecture Dual-Agent **Explorer + Critic** ;
* 93 endpoints API ;
* wallet Ed25519/Bech32 ;
* FAISS pour la recherche sémantique ;
* frontend React/Vite ;
* intégration OpenAI, Anthropic, Gemini, Ollama et Cursor.

### 4. Point très important : il faut maintenant distinguer **ARTCB fonctionnel** et **ARTCB économique/protocolaire**

C'est là que je vais être particulièrement critique.

Les éléments que nous avons travaillés ensemble :

* plafond **21 M ARTCB** ;
* émission démographique basée sur les **adultes humains vérifiés** ;
* HBP ;
* `10 % → 60 % → 20 %` ;
* `OwnerDecay` ;
* M1 à 100 % ;
* humain distinct pour les machines supplémentaires ;
* WorkID unique ;
* pré-blocs dynamiques ;
* règlement A/B ;
* Universal Workload ;
* identité humaine + identité machine/TPM ;
* confidentialité organisationnelle ;

**ne doivent pas être considérés automatiquement comme implémentés simplement parce qu'ils ont été simulés ou discutés.**

Le README actuel décrit surtout le système **mémoire/PoL/blockchain/API/agents/wallet**, tandis que notre modèle économique complet constitue une couche de protocole beaucoup plus spécifique.

---

# 5. Et concernant ton objectif de confidentialité entreprise

Je garde également comme exigence d'architecture ce que nous avons défini :

```text
                 ARTCB GLOBAL
                      │
          ┌───────────┼───────────┐
          │           │           │
        PUBLIC      ORG A       ORG B
                      │
                ┌─────┴─────┐
                │           │
              Groupe 1    Groupe 2
                │           │
             sous-groupes/users/agents
```

L'objectif n'est **pas** que le travail privé d'une entreprise soit publié dans le livre public mondial.

Il faut donc séparer :

1. **preuve publique minimale** ;
2. **données privées de l'organisation** ;
3. **droits d'accès internes** ;
4. **groupes/sous-groupes/utilisateurs/agents** ;
5. **identité cryptographique de l'organisation** ;
6. **preuve d'intégrité permettant éventuellement de vérifier qu'un travail privé existe sans révéler son contenu**.

C'est une architecture de type **confidentialité + vérifiabilité**, pas simplement un système de groupes RBAC. Les documents d'analyse du projet identifient déjà précisément cette nécessité. 

---

## 6. Mon verdict de mise à jour

**Le projet a franchi un niveau supplémentaire.**

Je classerais actuellement les couches ainsi :

| Couche                             | Situation                                               |
| ---------------------------------- | ------------------------------------------------------- |
| Blockchain / livre                 | **active**                                              |
| PoL / mémoire                      | **active et testée**                                    |
| API / frontend                     | **active**                                              |
| Wallet                             | **actif**                                               |
| PQC / crypto-agilité               | **présente mais à auditer précisément**                 |
| 4 nœuds                            | **preuves récentes disponibles**                        |
| Tests automatisés                  | **519/519 annoncé par le main**                         |
| Validation DV                      | **PASS annoncé pour DV-02/DV-06 sur 4 nœuds**           |
| Identité biométrique/WebAuthn      | **intégrée récemment**                                  |
| Tokenomics 21 M définitive         | **à distinguer du code fonctionnel actuel**             |
| HBP/OwnerDecay complet             | **à vérifier dans le code actuel**                      |
| Confidentialité multi-organisation | **architecture à poursuivre/auditer**                   |
| Universal Workload complet         | **à vérifier contre le code réel actuel**               |
| Certification mainnet complète     | **ne doit pas être déduite des seuls tests précédents** |

**Le prochain audit pertinent n'est donc plus un simple “est-ce que GitHub est à jour ?”.** Il faut maintenant faire un **audit croisé du `main` actuel du 3 septembre avec toutes les décisions ARTCB accumulées**, notamment le nouveau système biométrique, les 4 nœuds, les tests DV, la tokenomics 21 M, HBP/OwnerDecay et surtout le contrôle d'accès privé/public.

C'est cette comparaison qui permettra de dire précisément : **ce qui est réellement codé, ce qui est testé, ce qui est seulement documenté/simulé, et ce qui manque encore.**

# Audit suivant lancé — phase de contrôle croisé

**Expertises mobilisées :**

* Audit Git/GitHub et historique des commits
* Architecture blockchain et consensus distribué
* Sécurité réseau et cryptographie/PQC
* Tokenomics et modélisation économique
* Proof-of-Learning
* Identité humaine, matérielle et WebAuthn
* Contrôle d'accès multi-tenant
* Architecture Zero Trust et confidentialité
* Audit logiciel et cohérence spécification ↔ code ↔ tests

J'ai commencé directement sur le `main` actuel de [ARTCB — dépôt officiel](https://github.com/vgactech/artcb?utm_source=chatgpt.com).

## Verdict immédiat

**Le prochain audit doit être un audit de divergence.**

Car j'ai déjà identifié une divergence importante entre :

1. **les décisions officiellement enregistrées dans le dépôt** ;
2. **le README présenté comme état actuel du projet** ;
3. **le code réellement monté dans l'API**.

---

# 1. Point critique n°1 — le README est contradictoire avec les décisions protocolaires

Le README actuel annonce encore :

* récompense initiale : **1 ARTCB/bloc** ;
* halving fixe ;
* halving dynamique selon la vélocité IA ;
* fondateurs : `5 wallets × 210 000 ARTCB`.

Or le registre des décisions contient explicitement :

### D-024

* suppression du calendrier de halving ;
* émission géopopulation ;
* plafond absolu de **21 M** ;
* `R(H)` ;
* HBP confirmé.

### D-025

* première machine M1 = **100 % permanent** ;
* `OwnerDecay` pour les machines supplémentaires ;
* humain distinct ;
* maximum une machine externe ;
* émission normalisée dans le temps ;
* frais vers `UniversalDividendVault`.

### Conclusion

Le README **n'est pas actuellement une source fiable de vérité économique complète**.

Cela ne signifie pas automatiquement que le code est faux.

Cela signifie qu'il faut maintenant répondre précisément à trois questions :

> **Quelle règle est réellement exécutée par le code ?**

> **Quelle règle est seulement documentée ?**

> **Quelle documentation est devenue obsolète ?**

C'est maintenant une priorité de l'audit.

---

# 2. La bonne nouvelle : le registre des décisions est beaucoup plus avancé

Le fichier `DECISIONS_UTILISATEUR_ARTCB` contient effectivement les décisions que nous avons accumulées.

Il confirme notamment :

| Sujet                    | Décision enregistrée                |
| ------------------------ | ----------------------------------- |
| Supply                   | 21 000 000 maximum                  |
| Halving historique       | abrogé                              |
| Émission                 | géopopulation                       |
| Population               | adultes humains                     |
| HBP                      | 10 → 60 → 20                        |
| M1                       | 100 % permanent                     |
| Machines supplémentaires | OwnerDecay                          |
| Humain externe           | obligatoire                         |
| Limite                   | max 1 machine externe               |
| Work                     | WorkID unique                       |
| Pré-blocs                | dynamiques                          |
| Frais                    | UniversalDividendVault              |
| Validation               | règles V-01 → V-07 gelées par D-043 |
| Certification distribuée | distincte de la tokenomics          |

Donc, contrairement à ce que pourrait laisser croire le README :

**le référentiel décisionnel interne est beaucoup plus précis que la documentation d'accueil.**

---

# 3. État Git réellement observé

Le `main` actuel pointe sur :

```text
addc6e9e23e5da17701b0a63aba9b4ce62ec8140
```

Ce commit correspond à une publication Replit.

Les commits précédents confirment cependant plusieurs éléments importants.

### Validation distribuée

Un commit précédent indique :

```text
DV-02 et DV-06 PASS mesurés sur les 4 nœuds
Flood 64×4 = 200
locks 401
SSRF 400
netem OVH4 restauré
```

Cela constitue une **preuve de validation spécifique**, mais cela ne suffit pas à conclure automatiquement :

> « Tout le protocole mainnet est définitivement certifié. »

La certification doit toujours être vérifiée contre le mécanisme réel de la porte de certification.

---

# 4. Le code API montre que la certification est conçue comme une porte réelle

Dans `src/api/main.py`, l'état de certification est calculé via :

```text
certification_gate(load_dv_verdicts())
```

L'API expose ensuite notamment :

* `certified_distributed_mainnet`
* `certification_reason`
* `operator_certification_go`
* `dv_not_pass`

C'est important.

Cela signifie que le système ne repose pas uniquement sur un texte disant :

> « Nous sommes certifiés. »

Le logiciel possède un mécanisme destiné à calculer l'état à partir des résultats DV.

## Mais l'audit suivant devra vérifier une chose essentielle

Il faut maintenant ouvrir :

* le code de `devnet_validation.py` ;
* les fichiers `DV-*/RESULT.json` ;
* les conditions exactes de `certification_gate()` ;
* l'état actuel des résultats présents dans `main`.

C'est la seule manière de répondre définitivement :

### La certification est-elle réellement à `true` actuellement ?

ou :

### Les commits annoncent-ils seulement certains tests PASS sans que toutes les conditions soient satisfaites ?

---

# 5. Biométrie et WebAuthn : intégrés, mais audit de sécurité nécessaire

Les commits récents montrent :

* intégration WebAuthn ;
* inscription biométrique ;
* caméra locale ;
* interface `/register`.

Le code API importe effectivement :

```text
webauthn_routes
auth_routes
```

Donc ce n'est plus uniquement une idée ou une maquette documentaire.

**Une couche biométrique est réellement présente dans l'application.**

Mais l'audit ne doit pas s'arrêter là.

Il faut vérifier :

1. où sont stockées les données ;
2. si des données biométriques brutes quittent le navigateur ;
3. si WebAuthn utilise bien les authentificateurs matériels ;
4. quelle donnée devient réellement une preuve d'identité ;
5. comment empêcher la confusion entre :

   * authentification ;
   * identité humaine ;
   * unicité humaine ;
   * propriété d'un wallet.

C'est un point fondamental.

**WebAuthn ≠ preuve automatique qu'une personne est un humain unique mondial.**

---

# 6. Confidentialité organisationnelle : correction importante par rapport à l'ancien état

Le code actuel de `main.py` importe maintenant :

```text
groups_routes
privacy_routes
```

Cela indique une évolution importante par rapport à l'ancien audit.

L'ancien document `GROUPES_RESEAUX_ARTCB.md` disait explicitement que :

* les groupes n'existaient pas réellement ;
* les ACL étaient absentes ;
* le champ `visibility` était minimal ;
* le filtrage n'était pas réellement implémenté.

Mais le `main` actuel importe désormais des routes dédiées :

```text
src.api.groups_routes
src.api.privacy_routes
```

## Conclusion

L'ancien audit est maintenant insuffisant.

Il faut impérativement auditer le code actuel de :

* `groups_routes.py`
* `privacy_routes.py`
* modèles de données associés ;
* mécanismes d'autorisation ;
* stockage ;
* chiffrement ;
* propagation P2P.

Parce qu'il y a deux possibilités :

### Cas A — fonctionnalité réellement implémentée

Alors le projet a progressé fortement.

### Cas B — routes présentes mais sécurité incomplète

Alors nous avons potentiellement une **illusion de confidentialité**.

Et ce second cas serait beaucoup plus dangereux.

---

# 7. Le vrai audit suivant que je lance

Je vais donc structurer la prochaine phase autour de **6 vérifications croisées**.

## A — Audit de vérité du code

Pour chaque grande fonction :

```text
Décision
   ↓
Spécification
   ↓
Code
   ↓
Tests
   ↓
Résultat réellement mesuré
```

Nous allons éviter définitivement les conclusions du type :

> « c'est présent dans le README, donc c'est implémenté ».

---

## B — Audit tokenomics 21 M

Je vais vérifier dans le code réel :

### Supply

```text
21 000 000
```

### Émission

```text
R(H)
×
normalisation temporelle
```

### Et surtout :

* suppression effective du halving historique ;
* absence d'ancien mécanisme `extra_epochs` ;
* calcul des adultes vérifiés ;
* plafond impossible à dépasser ;
* HBP sans double émission ;
* OwnerDecay ;
* M1 ;
* machine externe ;
* WorkID ;
* règlement économique.

### Objectif

Construire ce tableau :

| Élément    | Décision | Code | Test | Verdict   |
| ---------- | -------- | ---- | ---- | --------- |
| 21 M       | oui      | ?    | ?    | à auditer |
| R(H)       | oui      | ?    | ?    | à auditer |
| HBP        | oui      | ?    | ?    | à auditer |
| OwnerDecay | oui      | ?    | ?    | à auditer |
| M1 100 %   | oui      | ?    | ?    | à auditer |
| WorkID     | oui      | ?    | ?    | à auditer |

---

# 8. Audit des 4 nœuds

Je vais séparer trois niveaux.

## Niveau 1 — preuve historique

Les commits et rapports indiquent que les validations ont été réalisées.

## Niveau 2 — état Git

Les quatre nœuds doivent être comparés à la version actuellement attendue.

## Niveau 3 — réalité réseau

Il faut vérifier :

```text
Node 1
   │
Node 2 ─── consensus
   │
Node 3
   │
Node 4
```

Les questions seront notamment :

* même protocole ?
* même genesis ?
* même chaîne ?
* même hauteur ?
* même hash final ?
* même politique crypto ?
* même résultat de certification ?

**Un commit Git n'est pas une preuve qu'un serveur distant exécute réellement ce commit.**

---

# 9. Audit de la confidentialité entreprise

C'est maintenant une priorité.

L'objectif final reste :

```text
                     ARTCB
                       │
        ┌──────────────┼──────────────┐
        │              │              │
      PUBLIC         ORG A          ORG B
                       │
               ┌───────┴───────┐
               │               │
            GROUP 1         GROUP 2
               │
           SUBGROUP
               │
        USER / AGENT
```

Mais nous devons maintenant vérifier si le code garantit réellement :

### Un utilisateur extérieur

```text
❌ ne peut pas lire les données ORG A
```

### Un membre ORG A

```text
✓ lit uniquement ses autorisations
```

### Un administrateur de groupe

```text
✓ gère son groupe
❌ ne lit pas automatiquement toute l'organisation
```

### Un agent

```text
✓ agit dans son périmètre
❌ n'obtient pas automatiquement les droits du propriétaire
```

### Le réseau public

```text
✓ peut éventuellement vérifier une preuve
❌ ne reçoit pas le contenu privé
```

C'est précisément la différence entre :

**RBAC simple**

et

**confidentialité cryptographique vérifiable multi-tenant**.

---

# 10. Premier problème déjà identifié : sources de vérité multiples

Actuellement, nous avons au moins :

```text
README
       │
TOKENOMICS_ARTCB
       │
DECISIONS_UTILISATEUR_ARTCB
       │
rapports/
       │
code/
       │
tests/
```

Et ils ne sont manifestement pas tous synchronisés.

C'est dangereux pour un protocole.

## Solution que je recommande

Créer explicitement une hiérarchie :

```text
                PROTOCOL SOURCE OF TRUTH
                         │
             DECISIONS VERSIONNÉES
                         │
              SPECIFICATION GELÉE
                         │
                     CODE
                         │
                    TESTS
                         │
              RAPPORTS MESURÉS
                         │
                README / MARKETING
```

Le README ne doit jamais pouvoir contredire le protocole actif.

---

# Mon verdict provisoire

## Ce qui est clairement confirmé

* le dépôt est actif ;
* le `main` a progressé ;
* les validations DV récentes sont documentées dans les commits ;
* la porte de certification existe dans le code ;
* WebAuthn est intégré ;
* les routes de groupes et de confidentialité existent désormais ;
* le registre décisionnel contient une tokenomics beaucoup plus avancée que le README.

## Ce qui est déjà suspect

* **README tokenomics contradictoire avec D-024/D-025** ;
* possible documentation obsolète ;
* il faut vérifier si la nouvelle tokenomics est réellement exécutée ;
* il faut vérifier si les groupes/confidentialité sont réellement sécurisés ;
* il faut vérifier la certification actuelle à partir des fichiers DV, pas seulement des messages de commit.

---

# Prochaine étape de l'audit

Je considère donc l'audit suivant comme officiellement orienté :

## **AUDIT ARTCB-208 — CODE ↔ DÉCISIONS ↔ TESTS ↔ RÉSEAU**

avec quatre verdicts séparés :

### 1. Fonctionnel

**Qu'est-ce qui fonctionne réellement ?**

### 2. Économique

**Quelle tokenomics est réellement exécutée ?**

### 3. Sécurité

**Qu'est-ce qui est réellement protégé et vérifié ?**

### 4. Confidentialité

**Quelles données peuvent réellement rester privées d'une organisation à l'autre ?**

La première anomalie critique est déjà établie : **la documentation publique et le référentiel décisionnel ne décrivent pas actuellement la même tokenomics**. La prochaine phase doit maintenant déterminer laquelle correspond au code réellement exécuté.

# Audit critique de ton constat — biométrie, wallets et vrai humain

**Expertises mobilisées :** cybersécurité, identité numérique, biométrie, WebAuthn/FIDO, cryptographie, sécurité blockchain, anti-Sybil, protection des données RGPD, conformité européenne et audit de protocoles.

J'ai vérifié le code et le rapport biométrique actuel du dépôt ARTCB. Ma conclusion est importante :

## Verdict immédiat

**Le fait que tu sois le créateur du projet et que tu aies toi-même créé tous les wallets ne supprime pas les exigences de sécurité du protocole.**

Mais il faut distinguer deux choses :

### 1. Pour ta phase de test contrôlée

Le fait que tu sois la seule personne à créer les comptes signifie que tu sais personnellement qui a effectué les tests.

### 2. Pour ce que le protocole prétend prouver

Le système doit être capable de le démontrer **sans dépendre de ta parole ou de ton rôle de créateur**.

C'est là que se situe actuellement la principale différence.

---

# 1. Ce que le système actuel prouve réellement

D'après le code et le rapport ARTCB actuellement vérifiés, il existe deux mécanismes différents.

## A — Face ID / empreinte via WebAuthn

Le système utilise un authentificateur de plateforme.

Le flux est approximativement :

```text
Humain
   │
   ▼
Téléphone / ordinateur
   │
   ├── Face ID / empreinte / Windows Hello
   │
   ▼
Secure hardware / authenticator
   │
   ▼
WebAuthn
   │
   ▼
Signature cryptographique
   │
   ▼
Serveur ARTCB
   │
   ▼
Création / accès wallet
```

Le serveur ne reçoit normalement pas ton empreinte ou ton visage brut. Il reçoit une preuve cryptographique liée à l'authentificateur. Le code vérifie notamment le challenge, l'origine, la présence/utilisation de l'utilisateur et la signature cryptographique. Le compteur de signature est aussi utilisé pour détecter certains scénarios de rejeu. ([NIST Pages][1])

**C'est une bonne base pour authentifier une personne possédant un appareil et capable de satisfaire le mécanisme biométrique local.**

---

# 2. Mais voici le problème fondamental : biométrie ≠ identité humaine vérifiée

C'est probablement le point le plus important de ton projet.

Le système actuel peut dire :

> « Une authentification WebAuthn valide a été réalisée sur cet appareil. »

Mais il ne peut pas automatiquement dire :

> « Cette personne est un humain unique, réel, vivant et distinct de tous les autres humains du réseau. »

Ce sont deux affirmations totalement différentes.

| Question                                           | WebAuthn seul                                               |
| -------------------------------------------------- | ----------------------------------------------------------- |
| Une authentification cryptographique a réussi ?    | Oui                                                         |
| L'utilisateur a validé localement l'opération ?    | Oui, selon l'authentificateur                               |
| Une personne était probablement présente ?         | Partiellement                                               |
| C'est un humain vivant ?                           | Pas forcément démontré                                      |
| C'est la même personne que lors de l'inscription ? | Selon le mécanisme local, pas comme identité civile globale |
| Cette personne n'a pas déjà un autre compte ?      | Pas démontré automatiquement                                |
| C'est une personne unique dans tout ARTCB ?        | Non démontré                                                |
| Une seule personne ne contrôle pas 100 identités ? | Non démontré                                                |

---

# 3. Ton observation sur la vitesse de l'enregistrement est donc très importante

Tu dis :

> « L'enregistrement facial est allé super vite. Qu'est-ce qui me prouve que cela s'est bien passé ? »

La réponse critique est :

## Une opération rapide n'est pas une preuve que toutes les vérifications de sécurité ont été effectuées.

Elle peut simplement signifier :

```text
Demande créée
      ↓
Caméra ouverte
      ↓
Visage détecté
      ↓
liveness_ok = true
      ↓
wallet créé
```

Or le rapport ARTCB décrit actuellement la voie caméra comme une détection locale avec preuve `liveness_ok` et un secret d'appareil, sans transmission d'image brute au serveur.

Le rapport précise lui-même que cette voie signifie essentiellement qu'un visage était détecté dans le cadre, et qu'elle n'est pas équivalente à une véritable vérification biométrique centralisée ou à une preuve d'identité humaine unique.

**C'est donc actuellement le point le plus critique à ne pas confondre.**

---

# 4. Ce qui manque actuellement dans le flux : la preuve indépendante d'un humain réel

Pour atteindre l'objectif que tu décris, il faut séparer plusieurs niveaux.

## Niveau 1 — Détection d'un visage

```text
La caméra voit quelque chose qui ressemble à un visage.
```

Ce n'est pas suffisant.

Une photo peut potentiellement être utilisée.

Un écran peut montrer une vidéo.

Une vidéo peut être synthétique.

Un masque peut exister.

---

## Niveau 2 — Détection de vivacité

La question devient :

> « Est-ce un vrai visage vivant présent maintenant devant le capteur ? »

Il faut alors une protection contre les **attaques de présentation**.

C'est précisément le domaine couvert par la famille ISO/IEC 30107 relative à la détection des attaques de présentation biométrique. ([ISO][2])

Exemples :

```text
Photo imprimée
        ❌

Photo sur écran
        ❌

Vidéo préenregistrée
        ❌

Deepfake en temps réel
        ❌ ou détection renforcée

Masque
        ❌

Vrai humain présent
        ✓
```

Le NIST indique également que, pour la reconnaissance faciale, la détection d'attaques de présentation est une protection importante et que la biométrie seule ne doit pas être traitée comme un secret. ([NIST Pages][1])

---

# 5. Mais même la vivacité ne suffit pas

Supposons que tu détectes parfaitement un vrai humain vivant.

Tu peux alors démontrer :

```text
Un humain vivant était devant cette caméra.
```

Mais tu ne sais toujours pas :

```text
Est-ce que cet humain possède déjà
une autre identité ARTCB ?
```

Exemple :

```text
Personne X
   │
   ├── Wallet 1
   ├── Wallet 2
   ├── Wallet 3
   └── Wallet 100
```

Si ton système HBP récompense la rareté humaine, c'est un problème majeur.

Il faut donc distinguer :

# Présence humaine

et

# Unicité humaine

Ce ne sont pas la même sécurité.

---

# 6. Le processus complet que je recommande

Voici le flux que je considère comme nécessaire pour ARTCB.

## PHASE 0 — Création de la demande

```text
Utilisateur
     │
     ▼
Demande de création d'identité
```

Le système génère :

* un identifiant temporaire ;
* un challenge cryptographique aléatoire ;
* une durée d'expiration ;
* un identifiant de session ;
* éventuellement une liaison à l'appareil.

Le challenge doit être unique et ne pouvoir être utilisé qu'une seule fois.

Cela protège contre les attaques de rejeu. ([NIST Pages][1])

---

# PHASE 1 — Vérification de l'environnement

Avant même le visage :

```text
Navigateur
     │
     ├── HTTPS
     ├── origine vérifiée
     ├── domaine vérifié
     └── appareil authentificateur
```

Il faut éviter :

```text
faux site
    ↓
vol de la procédure biométrique
```

WebAuthn est particulièrement intéressant parce qu'il lie la preuve cryptographique au domaine et utilise des challenges. ([NIST Pages][1])

---

# PHASE 2 — Vérification d'un authentificateur matériel

Idéalement :

```text
Humain
   +
Appareil
   +
Clé cryptographique
```

Donc :

```text
SOMETHING YOU ARE
       +
SOMETHING YOU HAVE
```

La biométrie doit idéalement déverrouiller une clé cryptographique, plutôt que devenir elle-même la clé.

Le NIST traite d'ailleurs la biométrie dans le cadre d'une authentification multi-facteurs avec un authentificateur physique. ([NIST Pages][1])

---

# PHASE 3 — Capture biométrique

À cette étape :

```text
caméra activée
```

Mais le système ne doit pas simplement faire :

```python
if face_detected:
    create_wallet()
```

Il faut une véritable machine à états :

```text
INIT
 ↓
CAMERA_READY
 ↓
FACE_DETECTED
 ↓
QUALITY_CHECK
 ↓
LIVENESS_CHALLENGE
 ↓
LIVENESS_VERIFIED
 ↓
UNIQUENESS_CHECK
 ↓
CRYPTOGRAPHIC_BINDING
 ↓
HUMAN_STATUS_PENDING
 ↓
WALLET_CREATED
```

Chaque transition doit être journalisée.

---

# PHASE 4 — Qualité de capture

Avant toute décision :

```text
visage suffisamment visible ?
lumière suffisante ?
résolution suffisante ?
occlusion excessive ?
plusieurs visages ?
```

Le système doit pouvoir répondre :

> Pourquoi la capture a été acceptée ?

et également :

> Pourquoi elle a été refusée ?

---

# PHASE 5 — Détection de vivacité renforcée

C'est ici que ton inquiétude doit être résolue.

Je recommande un challenge dynamique.

Exemple conceptuel :

```text
Le système génère aléatoirement :

Tourner la tête à gauche
        ↓
Cligner des yeux
        ↓
Regarder en haut
        ↓
Tourner à droite
```

Mais l'ordre doit être aléatoire.

Pourquoi ?

Parce qu'une vidéo préenregistrée pourrait connaître une séquence fixe.

Il faut donc :

```text
Challenge aléatoire
        +
Réponse en temps réel
        +
Expiration courte
```

L'objectif est :

```text
preuve de fraîcheur
```

c'est-à-dire :

> « cette interaction a été réalisée maintenant ».

---

# 7. Il faut aussi tester contre plusieurs types d'attaque

Le système ne devrait jamais être validé uniquement avec :

```text
vrai visage → accepté
```

Il faut aussi tester :

| Test                    | Résultat attendu      |
| ----------------------- | --------------------- |
| vrai humain             | accepté               |
| photo papier            | rejetée               |
| photo écran             | rejetée               |
| vidéo enregistrée       | rejetée               |
| vidéo d'un autre humain | rejetée               |
| deepfake                | testé explicitement   |
| masque                  | testé selon la menace |
| caméra virtuelle        | détectée ou limitée   |
| replay réseau           | rejeté                |
| challenge expiré        | rejeté                |
| challenge réutilisé     | rejeté                |

ISO/IEC 30107 fournit justement le cadre de référence pour caractériser les attaques de présentation biométrique. ([ISO][2])

---

# 8. Ensuite seulement : vérifier l'unicité

Voici la partie la plus délicate pour ARTCB.

Supposons :

```text
Wallet A
    │
    └── Humain vérifié
```

Puis une nouvelle inscription :

```text
Wallet B
    │
    └── même humain ?
```

Le protocole doit être capable de répondre :

```text
MATCH probable
      │
      ├── oui → procédure de résolution
      │
      └── non → nouvelle identité
```

Mais attention :

## Je ne recommande pas de mettre une empreinte biométrique brute sur la blockchain.

Jamais.

Même une blockchain privée pose un problème important : la biométrie est une donnée extrêmement sensible et ne peut pas simplement être considérée comme une donnée classique.

Le système actuel ARTCB fait correctement un point important : les images brutes ne sont pas censées être envoyées à l'API ni inscrites on-chain.

---

# 9. Le plus gros problème réglementaire potentiel : le RGPD

En Europe, le fait d'être créateur du projet **ne crée pas d'exception générale**.

La question importante est :

> Est-ce que les données biométriques permettent d'identifier une personne de manière unique ?

Si oui, on entre dans un traitement particulièrement sensible.

Et une deuxième question est essentielle :

> Est-ce que les tests concernent uniquement toi ?

Si tous les tests concernent uniquement toi et ton propre matériel, le contexte est très différent d'un système public qui commence à collecter les données biométriques d'autres personnes.

Mais dès que le système traite des utilisateurs externes :

```text
créateur
≠
autorisé à ignorer les obligations de sécurité et de protection des données
```

Il faut notamment examiner :

* finalité exacte ;
* nécessité ;
* minimisation des données ;
* durée de conservation ;
* sécurité ;
* information des utilisateurs ;
* droits d'accès et d'effacement lorsque juridiquement applicable ;
* analyse d'impact lorsque le traitement présente un risque élevé.

**Le point important : être en phase de test sur un réseau réel ne signifie pas automatiquement qu'on peut ignorer le RGPD ou les règles applicables.**

---

# 10. Ce que je considère actuellement comme insuffisamment démontré dans ARTCB

D'après le code et le rapport que j'ai vérifiés, voici ma grille critique.

| Élément                                                | État                     |
| ------------------------------------------------------ | ------------------------ |
| WebAuthn                                               | solide comme base        |
| Challenge cryptographique                              | présent                  |
| Expiration du challenge                                | présente                 |
| Protection origine / RP                                | présente                 |
| User verification                                      | présente                 |
| Compteur anti-rejeu                                    | présent                  |
| Pas d'image brute serveur                              | bon point                |
| Pas d'image brute on-chain                             | bon point                |
| Test avec authentificateur logiciel                    | présent                  |
| Test réel massif sur capteurs                          | pas démontré             |
| Liveness ISO certifiée                                 | non démontrée            |
| Test photo/vidéo/deepfake documenté                    | non démontré             |
| Preuve qu'un humain réel a effectué chaque inscription | insuffisamment démontrée |
| Unicité globale d'un humain                            | non démontrée            |
| Anti-double identité biométrique                       | non démontré             |
| Processus de contestation                              | à définir                |
| Audit indépendant biométrique                          | non démontré             |
| Métriques FAR/FRR/PAD                                  | non démontrées           |
| Tests démographiques                                   | non démontrés            |

Le rapport ARTCB indique également explicitement que les tests automatisés utilisent un authentificateur logiciel et non un véritable téléphone ou capteur biométrique dans la CI.

**Donc : le flux logiciel peut être testé, mais cela ne certifie pas encore la qualité biométrique réelle du système.**

---

# 11. Un problème supplémentaire que tu as peut-être oublié : qui a créé le wallet ?

Tu as dit que :

> « tous les wallets ont été créés par moi ».

Il faut distinguer trois identités.

```text
┌──────────────────────────┐
│ QUI CRÉE LE WALLET ?     │
└────────────┬─────────────┘
             │
             ▼
        Créateur
             │
             │ peut être différent
             ▼
┌──────────────────────────┐
│ QUI POSSÈDE LE WALLET ?  │
└────────────┬─────────────┘
             │
             │ peut être différent
             ▼
┌──────────────────────────┐
│ QUI CONTRÔLE LA CLÉ ?    │
└──────────────────────────┘
```

Ces trois choses doivent être séparées.

Exemple :

```text
Toi
 │
 ├── crées Wallet A
 │
 ├── crées Wallet B
 │
 └── crées Wallet C
```

Le protocole ne peut pas automatiquement conclure :

```text
A = humain différent
B = humain différent
C = humain différent
```

Simplement parce que les wallets ont des noms différents.

---

# 12. Autre problème très important : le seed/private key

Le code actuel de création du wallet mérite une attention particulière.

Lorsqu'un nouveau wallet est créé, une clé de signature est générée. Le rapport de code indique que la biométrie sert à déverrouiller le mécanisme local, tandis que la seed reste l'élément critique du contrôle cryptographique du wallet.

Cela signifie qu'il faut impérativement vérifier :

```text
QUI voit la seed ?
```

```text
QUI peut l'exporter ?
```

```text
QUI peut restaurer le wallet ?
```

```text
EST-ELLE affichée dans une réponse API ?
```

```text
EST-ELLE journalisée ?
```

```text
EST-ELLE stockée temporairement quelque part ?
```

Le rapport rappelle explicitement que la biométrie n'est pas la seed et ne doit pas être confondue avec la clé privée.

C'est fondamental.

---

# 13. Le processus doit se répéter, mais pas de la même manière

Tu demandes :

> « À quelles étapes le processus doit se répéter ? »

Je recommande trois catégories.

## A — Vérification initiale forte

Lors de la création :

```text
IDENTITÉ HUMAINE
        +
LIVENESS
        +
UNICITÉ
        +
DEVICE BINDING
        +
WEBAUTHN
        ↓
HUMAN ID CREATED
```

C'est la phase la plus forte.

---

## B — Vérification normale

Lors des connexions quotidiennes :

```text
Wallet
   ↓
WebAuthn
   ↓
Biométrie locale
   ↓
Signature cryptographique
   ↓
Accès
```

Il ne faut pas refaire une vérification d'identité complète à chaque transaction.

Ce serait inutile et potentiellement excessif du point de vue des données.

---

## C — Re-vérification renforcée

Elle doit être déclenchée lorsque le risque augmente.

Par exemple :

```text
Nouvel appareil
      │
      ▼
RÉAUTHENTIFICATION
```

```text
Changement inhabituel de matériel
      │
      ▼
RÉAUTHENTIFICATION
```

```text
Tentative de récupération du wallet
      │
      ▼
VÉRIFICATION FORTE
```

```text
Détection d'un comportement Sybil
      │
      ▼
REVUE
```

```text
Tentatives répétées
      │
      ▼
RATE LIMIT + LOCK
```

```text
Suspicion de clonage
      │
      ▼
REVUE RENFORCÉE
```

---

# 14. Je recommande une vraie machine d'état ARTCB

Pas seulement :

```text
registered = true
```

Mais :

```text
PENDING
   ↓
DEVICE_BOUND
   ↓
WEBAUTHN_VERIFIED
   ↓
LIVENESS_PENDING
   ↓
LIVENESS_VERIFIED
   ↓
UNIQUENESS_PENDING
   ↓
HUMAN_VERIFIED
   ↓
ACTIVE
```

Et également :

```text
ACTIVE
   │
   ├── RISK_DETECTED
   │
   ├── RECOVERY_REQUESTED
   │
   ├── REVERIFICATION_REQUIRED
   │
   └── SUSPENDED
```

Cela permet d'éviter une erreur fréquente :

> créer définitivement une identité dès qu'une seule opération caméra réussit.

---

# 15. Les preuves doivent être conservées sous forme de preuves, pas nécessairement sous forme de biométrie

Je recommande une distinction stricte.

## Ce qui peut être conservé comme preuve technique

```text
verification_id
timestamp
protocol_version
challenge_hash
device_public_key
WebAuthn credential ID
verification_result
liveness_result
PAD_engine_version
risk_score
audit_hash
```

Mais pas :

```text
photo brute
vidéo brute
empreinte brute
```

sauf nécessité exceptionnelle, avec une architecture juridique et de sécurité spécifique.

---

# 16. Une chose essentielle que tu n'as pas explicitement demandée : la reproductibilité de l'audit

Tu dois pouvoir reprendre n'importe quelle inscription et répondre :

> Pourquoi cette identité a été acceptée ?

Il faut donc produire un journal d'audit.

Exemple :

```json
{
  "verification_id": "...",
  "time": "...",
  "protocol": "human-verification-v3",
  "challenge_used": true,
  "challenge_reused": false,
  "webauthn_uv": true,
  "webauthn_up": true,
  "liveness": "pass",
  "uniqueness": "pending_or_pass",
  "wallet_created": true
}
```

Les journaux d'authentification et des échecs doivent être surveillés afin de détecter les attaques et les anomalies. ([OWASP Cheat Sheet Series][3])

---

# 17. Ce que je te conseille maintenant pour ARTCB

## Priorité 1 — Ne pas appeler la caméra actuelle une preuve absolue d'identité humaine

La formulation correcte serait plutôt :

> **« Vérification de présence faciale locale »**

et non :

> **« Humanité unique cryptographiquement prouvée »**

tant que les couches supplémentaires ne sont pas implémentées et validées.

---

## Priorité 2 — Séparer officiellement les niveaux

Je recommande quatre statuts.

### Niveau 0

```text
WALLET_CREATED
```

Wallet créé.

Aucune affirmation sur l'humain.

---

### Niveau 1

```text
DEVICE_AUTHENTICATED
```

WebAuthn ou authentificateur matériel vérifié.

---

### Niveau 2

```text
LIVE_HUMAN_VERIFIED
```

Liveness robuste contre les attaques de présentation.

---

### Niveau 3

```text
UNIQUE_HUMAN_VERIFIED
```

Le protocole possède une méthode documentée pour gérer les doublons et la résistance Sybil.

---

# 18. Ma conclusion sur les wallets que tu as déjà créés

**Je ne dirais pas qu'ils sont nécessairement invalides.**

Je dirais plutôt :

```text
VALIDES POUR TEST TECHNIQUE
```

mais :

```text
PAS ENCORE SUFFISAMMENT PROUVÉS
COMME IDENTITÉS HUMAINES UNIQUES
```

C'est une distinction essentielle.

Le fait que tu les aies personnellement créés est une information opérationnelle utile pour toi, mais **ce n'est pas une preuve cryptographique universellement vérifiable par le réseau**.

---

# Ce que tu avais oublié de demander et qui doit absolument être inclus

## Checklist complète supplémentaire

* preuve d'humain vivant ;
* protection photo ;
* protection vidéo ;
* protection écran ;
* protection deepfake ;
* protection masque ;
* challenge aléatoire ;
* challenge à usage unique ;
* expiration ;
* anti-rejeu ;
* authentification de l'appareil ;
* liaison cryptographique wallet ↔ authentificateur ;
* détection du changement d'appareil ;
* récupération sécurisée ;
* détection des doublons humains ;
* procédure de contestation ;
* révocation ;
* réinscription ;
* perte d'appareil ;
* vol d'appareil ;
* perte de wallet ;
* succession/récupération éventuelle ;
* journal d'audit ;
* tests indépendants ;
* métriques de faux positifs et faux négatifs ;
* tests contre attaques réelles ;
* tests démographiques ;
* minimisation des données ;
* politique de conservation ;
* DPIA/analyse d'impact si applicable ;
* séparation stricte entre identité humaine, appareil et wallet ;
* séparation entre créateur, propriétaire et contrôleur de la clé ;
* aucun privilège spécial implicite pour le créateur du projet.

## Mon verdict critique

**ARTCB possède déjà une base intéressante avec WebAuthn, challenge, vérification cryptographique, contrôle d'origine et refus des images biométriques brutes.**

Mais la vitesse de l'inscription faciale que tu as observée révèle précisément une question qui doit maintenant être auditée :

> **Le système a-t-il simplement détecté un visage et créé un wallet, ou a-t-il réellement exécuté toutes les étapes nécessaires pour soutenir une affirmation de “humain réel, vivant et unique” ?**

**À partir de ce que j'ai vérifié, la deuxième affirmation n'est pas encore démontrée complètement.** Le système actuel est beaucoup plus solide pour l'**authentification biométrique locale / WebAuthn** que pour la **preuve d'un humain unique à l'échelle du réseau**. ([NIST Pages][1])

La prochaine étape logique est donc un **audit de divergence spécifique “Biometric Enrollment → Human Proof → Wallet Creation”**, fichier par fichier, pour vérifier exactement **à quel moment chaque wallet existant a été créé, quelle méthode a été utilisée, quelles preuves existent réellement, et quelles garanties le système n'a pas effectivement exécutées**.

[1]: https://pages.nist.gov/800-63-4/sp800-63b.html?utm_source=chatgpt.com "NIST Special Publication 800-63B"
[2]: https://www.iso.org/standard/83828.html?utm_source=chatgpt.com "ISO/IEC 30107-1:2023 - Information technology — Biometric presentation attack detection — Part 1: Framework"
[3]: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html?utm_source=chatgpt.com "Authentication - OWASP Cheat Sheet Series"

