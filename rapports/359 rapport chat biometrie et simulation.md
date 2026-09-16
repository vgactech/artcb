Oui. J’ai repris le dépôt **directement sur GitHub**, puis recroisé le `main` actuel avec les rapports récents sur l’inscription, la biométrie, le wallet, le USER↔NODE, l’ORG/KYB et les matrices de certification. Je n’ai effectué **aucune modification**.

GitHub — [dépôt ARTCB `vgactech/artcb`](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

# 1. État GitHub au moment de cet audit

Le `main` actuel est maintenant :

**`093d697b241b637bc6d13812fe7bb1677ab013e8` — 15 septembre 2026 10:55 UTC.**

Le dernier commit concerne **Bob → ARTCB / `JOB_COMPLETED`**, et non une nouvelle implémentation de l'inscription, de la biométrie, de la validation humaine ou de l'ORG/KYB.

C'est important : **les rapports R343–R352 ne constituent donc pas tous l'état final du `main` actuel**. Certains ont été écrits quelques commits auparavant. Le dernier `main` ajoute surtout le chantier Bob/JOB_COMPLETED.

---

# 2. Ta question principale : le nouveau parcours d'inscription est-il réellement dans l'UI ?

## Réponse : **oui pour une partie du parcours, non pour le parcours complet que tu décris.**

L'UI actuelle possède bien une page dédiée :

`frontend/src/pages/RegisterBiometric.tsx`.

Elle permet actuellement :

* inscription par **empreinte/WebAuthn** ;
* inscription par **visage** ;
* inscription par **les deux** ;
* connexion par empreinte ;
* connexion par visage ;
* création/récupération de la session ;
* affichage de l'adresse du wallet ;
* et, lors de certaines créations, retour du `seed_hex`.

Le code utilise notamment :

```text
webauthnRegisterOptions()
        ↓
création credential plateforme
        ↓
webauthnRegisterVerify()
        ↓
session + wallet
```

Pour la caméra :

```text
faceEnrollOptions()
        ↓
caméra
        ↓
liveness_ok = true
        ↓
faceEnrollVerify()
        ↓
session + wallet
```

Donc **l'inscription wallet + authentification biométrique existe réellement dans l'UI**.

---

# 3. Mais il y a une différence fondamentale avec le processus que tu viens de décrire

Tu décris :

```text
1. Inscription
      ↓
2. Création du wallet
      ↓
3. Clé publique / clé privée
      ↓
4. Validation biométrique
      ↓
5. Validation faciale
      ↓
6. Validation distribuée
      ↓
7. ~100 validateurs humains
      ↓
8. identité validée
```

**Ce n'est pas le flux actuellement implémenté.**

Le système actuel fait plutôt :

```text
INSCRIPTION
   │
   ├── WebAuthn
   │     └── credential cryptographique
   │
   ├── empreinte
   │
   ├── Face ID / authentificateur OS
   │
   └── caméra
         └── présence faciale locale
                ↓
             WALLET
                ↓
          SESSION AUTH
```

Et surtout :

> **WebAuthn/Face ID/empreinte ne constituent actuellement pas une preuve `UNIQUE_HUMAN`.**

Le rapport R345 le dit explicitement : aucune table `HumanIdentity` n'est actuellement utilisée pour transformer l'inscription biométrique en identité humaine unique. `UNIQUE_HUMAN=false`.

---

# 4. Ce que la biométrie valide actuellement

Il faut être extrêmement précis ici.

### Empreinte / Face ID

Le serveur vérifie une **credential cryptographique WebAuthn**.

Cela signifie :

```text
appareil
   ↓
authentificateur
   ↓
clé privée WebAuthn
   ↓
signature
   ↓
serveur
   ↓
vérification avec clé publique
```

La biométrie locale sert principalement à **déverrouiller l'authentificateur**.

Le serveur ne reçoit donc pas ton empreinte ou ton visage brut.

Le code actuel est bien présent dans :

* `frontend/src/lib/webauthn.ts`
* `src/api/webauthn_routes.py`
* `src/artcb/security/webauthn_protocol.py`
* `src/artcb/security/webauthn_store.py`
* `frontend/src/pages/RegisterBiometric.tsx`
* `frontend/src/components/FaceCapture.tsx`.

### Caméra

C'est encore différent.

La caméra actuelle ne fait **pas** une reconnaissance faciale mondiale.

Elle fait essentiellement :

```text
caméra
 ↓
détection / liveness locale
 ↓
liveness_ok=true
 ↓
secret appareil
 ↓
serveur
```

Le rapport précise explicitement que ce n'est **pas** une biométrie serveur et que cela signifie seulement qu'une présence faciale locale a été détectée.

---

# 5. Et c'est justement pour cela que l'UI affiche désormais honnêtement la limite

Le rapport 215 a ajouté :

```text
ASSURANCE_LEVELS

password              = 0
face_camera            = 1
webauthn_fingerprint   = 2
webauthn_face          = 2
unique human verified  = 3
```

Mais **aucune méthode actuelle n'atteint le niveau 3**.

L'API expose même :

```text
unique_human_proven: false
```

et l'interface a été modifiée pour parler de :

> **« présence faciale locale »**

plutôt que de prétendre qu'il s'agit d'une reconnaissance faciale prouvant l'identité humaine unique.

C'est une modification importante et elle a bien été implémentée.

---

# 6. Le binding appareil a également été réellement intégré à l'UI

C'est un autre point que nous avions identifié précédemment.

Avant R345 :

```text
utilisateur
   ↓
serveur OVH
   ↓
empreinte serveur
```

Donc un wallet créé par un agent sur le serveur pouvait empêcher les autres créations.

R345 a changé cela en :

```text
navigateur
   ↓
localStorage
   ↓
X-ARTCB-Device-Id
   ↓
empreinte client
   ↓
wallet
```

Le `frontend/src/api/client.ts` ajoute effectivement le `X-ARTCB-Device-Id` à chaque requête. Le commit R345 modifie également `frontend/dist` et `Wallets.tsx`.

Et cela a été testé en réel :

| Test                       |      Résultat |
| -------------------------- | ------------: |
| Device A → premier wallet  |       **200** |
| Device A → deuxième wallet |       **409** |
| Device B → premier wallet  |       **200** |
| Binding client             | **LIVE PASS** |

Donc cette partie-là est **réellement implémentée et mesurée**.

---

# 7. Mais où est la validation par les « 100 validateurs » ?

## C'est ici que la réponse devient importante : **je n'ai trouvé aucune implémentation actuelle correspondant à ce mécanisme.**

J'ai recherché :

* validation humaine ;
* validateurs ;
* HBP ;
* `ValidatorAssignment` ;
* `ValidatorDecision` ;
* validation distribuée ;
* `CERTIFIED_100` ;
* validation d'identité ;
* validation après inscription.

Je trouve bien des **spécifications**, mais pas le mécanisme complet opérationnel permettant :

```text
Human A
   ↓
inscription
   ↓
preuves biométriques
   ↓
demande de validation
   ↓
sélection de 100 validateurs indépendants
   ↓
100 décisions
   ↓
quorum
   ↓
HumanIdentity = VERIFIED
```

Et je ne vais donc pas prétendre que cela existe.

---

# 8. Attention : `CERTIFIED_100` ne signifie PAS « 100 validateurs humains »

C'est une confusion importante à éviter.

Dans le projet actuel :

```text
CERTIFIED_100
```

désigne la **certification globale du système/protocole**, avec différentes conditions techniques et live.

Ce n'est pas :

```text
100 personnes ont validé cet utilisateur.
```

La matrice actuelle définit notamment :

```text
C0 = spécification
C1 = code
C2 = tests unitaires
C3 = live 1 nœud
C4 = live 4 nœuds
C5 = preuve distribuée reproductible
C6 = certification finale
```

Le rapport R352 confirme que `CERTIFIED_100=false`.

Donc il faut **absolument séparer** :

### Certification du réseau

```text
CERTIFIED_100
```

et :

### Certification d'un humain

```text
UNIQUE_HUMAN / HumanIdentity
```

et éventuellement :

### Validation d'une organisation

```text
ORG_VALIDATED / KYB
```

Ce sont trois systèmes différents.

---

# 9. Le problème actuel de `HumanIdentity`

C'est probablement **le plus gros trou fonctionnel par rapport à ton architecture cible**.

R345 dit explicitement :

```text
HumanIdentity = absent comme mécanisme requis
UNIQUE_HUMAN = false
```

Et R348 confirme :

```text
HumanRegistry = présent
mais
non requis pour wallet creation
```

Donc actuellement :

```text
HumanRegistry
     │
     X
     │
wallet/create
```

n'est pas encore :

```text
HumanIdentity
     ↓
wallet
```

R348 a ajouté une autre couche :

```text
USER ↔ NODE
```

avec challenge + signature, mais **pas encore USER ↔ WALLET** et pas encore `UNIQUE_HUMAN`.

Le rapport indique explicitement :

> `R349 USER↔WALLET` — non livré
> `UNIQUE_HUMAN` — non livré
> preuve live multi-nœud — non livrée.

---

# 10. Donc ton processus actuel réel ressemble à ceci

```text
                    ┌─────────────────────┐
                    │     INSCRIPTION     │
                    └──────────┬──────────┘
                               │
                    création du wallet
                               │
             ┌─────────────────┴─────────────────┐
             │                                   │
       WebAuthn                              Caméra
             │                                   │
     empreinte / Face ID                présence faciale
             │                                   │
             └─────────────────┬─────────────────┘
                               │
                         AUTHENTIFICATION
                               │
                               ▼
                           WALLET
                               │
                               │
                    ┌──────────▼──────────┐
                    │ HumanIdentity ?     │
                    │                      │
                    │ actuellement        │
                    │ NON REQUIS           │
                    └──────────┬──────────┘
                               │
                               ▼
                       UNIQUE_HUMAN=false
```

**La branche suivante de ton architecture :**

```text
UNIQUE_HUMAN
      ↓
100 validateurs ?
      ↓
quorum ?
      ↓
HumanIdentity VERIFIED
```

**n'est pas encore raccordée à ce flux dans le code actuel que j'ai trouvé.**

---

# 11. Et le point « clé publique + clé privée » est également à clarifier

Il y a deux couples cryptographiques différents qu'il ne faut pas mélanger.

### A. Clé du wallet ARTCB

```text
Wallet
 ├── adresse
 ├── clé publique
 └── clé privée / seed
```

### B. Credential WebAuthn

```text
Authenticator
 ├── credential ID
 ├── clé publique WebAuthn
 └── clé privée WebAuthn
```

La biométrie locale sert principalement à protéger **B**.

Elle ne signifie pas automatiquement :

```text
biométrie
   ↓
clé privée du wallet ARTCB
```

Le rapport R345 insiste justement sur cette séparation et signale que le vault biométrique utilise un mot de passe aléatoire non affiché.

Donc **il ne faut pas considérer la clé privée du wallet comme le mécanisme qui valide biologiquement la personne**.

---

# 12. Maintenant, deuxième partie de ta question : ORG et associations

Là, il y a effectivement eu une modification importante.

## Ce qui est maintenant implémenté

R343/R345 ont ajouté le modèle ORG/KYB.

Le système distingue :

```text
HumanIdentity / KYC
          ≠
OrgIdentity / KYB
```

et :

```text
ORG_CREATED
      ≠
ORG_VALIDATED
      ≠
ORG_REWARD_ELIGIBLE
```

Le créateur **ne peut plus s'auto-valider**.

Le code actuel contient :

```python
creator_id == validator_id
        ↓
       DENY
```

et :

```text
validator ∈ controller
        ↓
       DENY

validator ∈ UBO
        ↓
       DENY
```

Cela est réellement dans `src/artcb/org/kyb.py`.

---

# 13. Donc ton ancienne règle « le créateur ne valide pas lui-même » a bien été intégrée

C'est précisément une correction que tu avais demandée.

Avant :

```text
A = créateur
A = validateur
      ↓
     BUG
```

La logique était inversée.

R345 l'a corrigée :

```text
A = créateur
A = validateur
      ↓
     DENY

A = créateur
B = validateur
      ↓
     ALLOWED
```

Le commit est explicite :

**`R345/R346: client device binding + KYB self-validate DENY`**.

---

# 14. MAIS : ta règle « seul le créateur et celui que le créateur nomme peuvent valider » n'est pas encore entièrement implémentée

C'est une nuance très importante.

Le système actuel dit essentiellement :

```text
créateur
   ≠
validateur
```

et :

```text
pas de conflit UBO/controller
```

Mais le modèle complet que tu décris est plus fort :

```text
Créateur ORG
     │
     ├── peut désigner Validator A
     │
     └── peut désigner Validator B
               │
               ▼
        seuls A/B peuvent valider
```

Je n'ai **pas trouvé ce système complet de délégation/nomination du validateur effectivement implémenté**.

Au contraire, la spécification KYB actuelle liste encore comme objets **« to implement »** :

```text
OrgApplication
DocumentRequirement
DocumentSubmission
ValidatorAssignment
ValidatorDecision
RiskAssessment
ConflictCheck
OrgValidation
```

C'est une preuve importante : **le modèle existe dans la spécification, mais l'implémentation complète n'est pas terminée.**

---

# 15. Où en est donc réellement l'ORG/KYB ?

| Fonction                            | État              |
| ----------------------------------- | ----------------- |
| Création ORG / Genesis              | **présente**      |
| séparation KYC / KYB                | **présente**      |
| `ORG_CREATED`                       | **présent**       |
| `KYB_PENDING`                       | **modélisé**      |
| `KYB_IN_REVIEW`                     | **modélisé**      |
| `KYB_APPROVED`                      | **modélisé**      |
| `ORG_ACTIVE`                        | **modélisé**      |
| UBO obligatoire dans la spec        | **oui**           |
| Documents bruts on-chain            | **non**           |
| Hash/commitment public              | **oui/scaffold**  |
| créateur auto-validation            | **DENY**          |
| conflit UBO/controller              | **DENY**          |
| nomination complète des validateurs | **pas démontrée** |
| `ValidatorAssignment` complet       | **non livré**     |
| `ValidatorDecision` complet         | **non livré**     |
| KYB live complet                    | **NON PROUVÉ**    |
| certification 100                   | **NON**           |

La spécification elle-même est marquée **SPEC + scaffold**, avec `CERTIFIED_100=false`.

Et R343 dit explicitement :

> **KYB complet live : NOT_PROVEN**.

---

# 16. Les rapports qui parlent précisément de tes modifications

Voici ceux que j'ai retrouvés et qui sont directement pertinents.

### **R208 — Biométrie / certification**

Rapport :

`208_biometric_cert_gate_2026-09-02.md`

Il décrit l'architecture WebAuthn, la caméra, les niveaux d'assurance, les tests et le fait que la biométrie ne constituait pas encore une preuve d'humain unique.

### **R215 — intégration des rapports 210 → 214**

C'est un rapport très important parce qu'il a intégré :

* assurance biométrique ;
* `unique_human_proven=false` ;
* audit enrollment → human proof → wallet ;
* UI ;
* correction du vocabulaire « présence faciale » ;
* dette encore ouverte.

### **R343 — Wallet + ORG/KYB + QR**

C'est le premier rapport récent directement consacré à ton nouveau chantier :

* wallet 409 ;
* ORG/KYB ;
* QR ;
* interdiction auto-validation ;
* `ORG_CREATED ≠ ORG_VALIDATED ≠ ORG_REWARD_ELIGIBLE`;
* KYB complet encore non prouvé.

### **R345 — inscription / identité**

C'est **le rapport le plus important pour ta question actuelle**.

Il documente :

* correction du binding appareil ;
* différence appareil/client vs serveur ;
* absence actuelle de `HumanIdentity` obligatoire ;
* biométrie ≠ `UNIQUE_HUMAN` ;
* vault biométrique ;
* problème du login password ;
* correction de `creator_may_self_validate`.

### **R346 — preuves live**

Il démontre réellement :

* binding client ;
* Device A / Device B ;
* `unique_human_proven=false` ;
* `HumanIdentity / UNIQUE_HUMAN : NON`.

### **R348 — USER ↔ NODE**

Il montre que la nouvelle couche USER↔NODE existe, mais que :

* USER↔WALLET reste ouvert ;
* UNIQUE_HUMAN reste ouvert ;
* preuve multi-nœud de cette association reste ouverte.

### **R352 — matrice de certification**

Il traite surtout la certification globale C0→C6, les problèmes de failover, TPM, USER↔NODE, etc., et maintient `CERTIFIED_100=false`.

---

# 17. Ce qui reste ouvert que je considère directement lié à ton parcours inscription → validation

Voici le tableau que je retiendrais maintenant.

| Chantier                                     | État actuel                                              |
| -------------------------------------------- | -------------------------------------------------------- |
| Inscription wallet classique                 | **fait**                                                 |
| Inscription WebAuthn                         | **fait**                                                 |
| Inscription caméra                           | **fait**                                                 |
| Empreinte + visage                           | **fait côté UI**                                         |
| Binding wallet ↔ appareil client             | **LIVE PASS**                                            |
| Authentification WebAuthn                    | **implémentée**                                          |
| Présence faciale locale                      | **implémentée**                                          |
| HumanIdentity réellement obligatoire         | **NON**                                                  |
| Unicité humaine globale                      | **NON**                                                  |
| Anti-double identité humaine                 | **NON**                                                  |
| Validation humaine distribuée                | **NON démontrée**                                        |
| 100 validateurs humains                      | **je n'ai trouvé aucune implémentation**                 |
| Quorum des validateurs humains               | **non trouvé**                                           |
| USER ↔ WALLET cryptographiquement verrouillé | **ouvert / R349**                                        |
| USER ↔ NODE                                  | **scaffold + tests, mais encore des preuves C5 à faire** |
| récupération autre appareil                  | **question ouverte**                                     |
| perte de wallet/appareil                     | **question ouverte**                                     |
| révocation/réinscription                     | **à compléter**                                          |
| contestation d'une identité                  | **à définir**                                            |
| ORG/KYB                                      | **scaffold**                                             |
| créateur auto-validation                     | **DENY implémenté**                                      |
| UBO/controller conflict                      | **DENY implémenté**                                      |
| nomination complète des validateurs ORG      | **non démontrée**                                        |
| ValidatorAssignment                          | **spec, pas implémentation complète**                    |
| ValidatorDecision                            | **spec, pas implémentation complète**                    |
| KYB live complet                             | **NOT_PROVEN**                                           |
| UI complète de validation humaine distribuée | **non trouvée**                                          |
| UI complète de workflow KYB                  | **non trouvée dans les éléments actuels retrouvés**      |

---

# 18. Et il y a plusieurs autres éléments des anciens audits que tu avais raison de ne pas vouloir perdre

J'en retiens notamment :

### A. USER ↔ WALLET

R348 a volontairement fait **USER ↔ NODE**, mais R349 USER ↔ WALLET reste explicitement non livré.

C'est essentiel pour ton architecture.

---

### B. HumanIdentity doit devenir la couche centrale

Actuellement :

```text
Wallet
   +
WebAuthn
   +
Face
```

mais pas encore :

```text
HumanIdentity
       │
       ├── wallet(s)
       ├── devices
       ├── authenticators
       └── validation state
```

C'est probablement la pièce architecturale qui manque pour relier correctement toutes tes demandes précédentes.

---

### C. La validation humaine ne doit pas être confondue avec WebAuthn

C'est déjà reconnu dans les rapports.

WebAuthn peut prouver :

```text
une credential valide
```

mais pas :

```text
cet humain est unique dans tout ARTCB
```

Le système actuel le documente honnêtement avec `unique_human_proven=false`.

---

### D. QR téléphone

Le QR existe comme **scaffold**, avec TTL et single-use, mais l'E2E téléphone réel reste `NOT_PROVEN`.

---

### E. Les tests biométriques réels

Les tests automatisés utilisent un **authenticator logiciel**, pas une flotte de téléphones/capteurs biométriques réels.

Donc :

```text
test logiciel WebAuthn
       ≠
preuve biométrique réelle à grande échelle
```

Ce point était déjà identifié dans l'audit biométrique et reste important. 

---

### F. USER↔NODE multi-nœuds

Le code existe, mais la preuve de cohérence multi-nœuds doit encore être transformée en preuve reproductible C5. R352 l'identifie également comme chantier de certification.

---

### G. Certification réseau

`CERTIFIED_100=false` reste actuel.

Et il y a même des éléments beaucoup plus bas niveau encore ouverts, notamment :

* failover producteur réellement capable de produire un bloc ;
* attestation TPM ;
* scripts C5 reproductibles ;
* coefficient de Nakamoto ≥ 100.

Ce sont des chantiers parallèles qui ne doivent pas être oubliés simplement parce que nous travaillons maintenant sur l'inscription.

---

# 19. Mon verdict actuel

## Ce qui a réellement avancé

**Oui**, l'UI et le backend ont été mis à jour pour une partie substantielle du nouveau parcours :

```text
inscription
   ↓
wallet
   ↓
WebAuthn / empreinte / Face ID
   ↓
caméra / présence faciale locale
   ↓
session
```

Et le **binding client appareil** a réellement été corrigé et validé en live.

## Ce qui n'est PAS encore fait

En revanche, ton architecture complète :

```text
inscription
 ↓
wallet
 ↓
clé cryptographique
 ↓
biométrie
 ↓
visage
 ↓
HumanIdentity
 ↓
100 validateurs indépendants
 ↓
quorum
 ↓
identité humaine certifiée
```

**n'est pas encore implémentée de bout en bout.**

Le plus gros trou est :

> **le passage entre « j'ai authentifié une credential / un appareil / une présence faciale » et « ce wallet appartient à un humain unique validé par le protocole ».**

Et je n'ai trouvé **aucune preuve actuelle permettant de dire que les 100 validateurs humains sont déjà opérationnels**.

Pour les organisations, c'est similaire :

```text
ORG_CREATED
    ↓
KYB
    ↓
validator indépendant
    ↓
ORG_VALIDATED
```

est **spécifié et partiellement scaffoldé**, avec l'interdiction d'auto-validation du créateur réellement corrigée, mais **le workflow complet de sélection/nomination des validateurs, leurs décisions, le quorum et la validation KYB live ne sont pas encore démontrés**.

### Point important sur le `main`

Le dernier `main` du 15 septembre est déjà allé plus loin sur d'autres chantiers — notamment Bob/JOB_COMPLETED — mais **je ne vois pas dans les commits post-R348/R352 une nouvelle implémentation qui fermerait ces trous inscription → HumanIdentity → validateurs ou ORG/KYB complet**. Le dernier commit est consacré à la persistance `JOB_COMPLETED`.

Donc, à cet instant, **je classerais le chantier “inscription/validation/authentification” en trois états distincts :**

**VERT — implémenté :** wallet, WebAuthn, présence faciale locale, session, binding client-device.

**ORANGE — scaffoldé/partiellement implémenté :** USER↔NODE, HumanRegistry, ORG/KYB, QR pairing.

**ROUGE — encore non implémenté/non démontré :** `UNIQUE_HUMAN`, USER↔WALLET complet, validation humaine distribuée par quorum/100 validateurs, workflow KYB complet avec assignment/decision live, et certification de ces mécanismes sur les quatre nœuds.
