Oui. J’ai repris le dépôt distant avant de répondre, et je corrige le point important : **tu avais raison sur le fait que la règle des 100 validations humaines avait été étudiée et retenue bien avant les rapports 208–215.**

Le dépôt actuel est `vgactech/artcb`, branche `main`, et son dernier commit est `093d697b...`, du 15 septembre 2026. Aucun changement n’a été effectué.

## 1. Ce que l’historique ARTCB confirme réellement

Ce n’est pas seulement le rapport 162.

En recherchant l’historique et les rapports antérieurs, je retrouve explicitement la règle :

* `Q = 100`
* **100 attestations distinctes**
* contrôle anti-collusion
* cycle `INSCRIT → FINDER_PENDING → VERIFIED → MATURED`
* récompense calculée/réservée mais **non transférable avant certification**
* mécanisme Finder/HBP
* traitement particulier du bootstrap Genesis
* révalidation lorsque le réseau dépasse le seuil de 100 validateurs.

Les rapports **133, 134, 135, 136, 137, 138, 139, 140, 141**, puis le rapport **162** et les simulations associées documentent cette construction. Par exemple, le rapport 135 précise déjà les **100 attestations distinctes**, le contrôle anti-collusion et les états du cycle.

Le rapport 136 confirme encore explicitement `Q=100`, les 100 attestations distinctes, l'anti-collusion et le cycle `FINDER_PENDING → VERIFIED → MATURED`.

Le rapport 137 précise même que `FINDER_PENDING` exige **100 attestations distinctes**, puis `VERIFIED` 100 attestations acceptées avec contrôles anti-collusion.

Et la simulation du rapport 162 existe toujours dans le dépôt actuel, notamment `simulations/20260828T174810Z_rapport162/out/03_hbp_finder.json`, avec `Q: 100`.

Donc je verrouille désormais cette distinction :

> **Les 100 validateurs humains ne sont pas une idée nouvelle que nous sommes en train d'inventer aujourd'hui. C'est une règle historique du modèle ARTCB qui a été étudiée, simulée, documentée et partiellement implémentée.**

---

# 2. Mais il faut distinguer 4 niveaux

C'est ici que se trouvait le problème dans les audits précédents.

| Élément                                                   | État                      |
| --------------------------------------------------------- | ------------------------- |
| Concept Q=100                                             | **Établi historiquement** |
| Modèle Finder/HBP                                         | **Établi**                |
| Simulations Q=100                                         | **Présentes**             |
| Code `Q_FINDER = 100`                                     | **Présent actuellement**  |
| 100 validations réellement distinctes dans le code actuel | **NON démontré**          |
| 100 humains réellement sélectionnés aléatoirement         | **NON démontré**          |
| 100 validations humaines live                             | **NON démontré**          |
| Certification mainnet réellement `100/100`                | **NON démontrée**         |

Le code actuel contient effectivement :

```text
Q_FINDER = 100
```

et le module se présente lui-même comme :

> `Identity / Finder Q=100 — rapport 162`

Mais il existe une faille conceptuelle majeure dans cette implémentation actuelle : `add_finder_validation(human_id)` **ne reçoit pas l'identité du validateur**. Il incrémente simplement un compteur.

Donc :

```text
validation_count = 100
```

ne signifie pas nécessairement :

```text
100 humains différents ont validé.
```

C'est une différence fondamentale.

**Il faut donc conserver la décision Q=100 historique, mais refaire son implémentation autour de 100 ValidatorHumanID distincts.**

---

# 3. Ton nouveau modèle de fonctionnement est cohérent — avec une correction importante

Je reformule ton architecture cible.

## ÉTAPE A — Création normale du wallet

```text
Humain
   ↓
création wallet
   ↓
WalletID
   ↓
clé publique + clé privée
```

Le wallet peut donc exister initialement.

Mais :

```text
wallet sans preuve biométrique
        ↓
wallet utilisable de manière limitée
        ↓
PAS de liaison à un node
        ↓
PAS de récompense transférable
```

C'est une séparation très importante.

---

# 4. Wallet + empreinte = Human Proof

Tu veux ensuite :

```text
Wallet
   +
empreinte digitale
   ↓
Human Proof
```

Ce Human Proof devient la condition permettant de passer à l'étape suivante.

Donc :

```text
Wallet seul
    → insuffisant

Wallet + empreinte digitale
    → humain pré-certifié
    → autorisation de liaison à un node
    → possibilité de demander certification Q=100
```

Je trouve cette séparation beaucoup plus propre que le modèle actuel.

---

# 5. L'inscription biométrique doit-elle être obligatoire immédiatement ?

**Oui, si ton objectif est réellement "un humain = un wallet".**

Il existe deux modèles possibles.

### Modèle 1 — biométrie après création

```text
création wallet
      ↓
wallet non certifié
      ↓
empreinte obligatoire
      ↓
Human Proof
```

Avantage : l'utilisateur peut commencer la création.

Inconvénient : il existe temporairement des wallets sans identité humaine.

### Modèle 2 — biométrie obligatoire dans le même parcours

```text
INSCRIPTION
   ↓
création wallet
   ↓
empreinte digitale obligatoire
   ↓
HumanID
   ↓
wallet lié à HumanID
```

Pour ARTCB, **je recommande le modèle 2 si l'objectif est de garantir dès l'origine l'invariant `1 humain → 1 wallet`.**

Il faut cependant conserver la possibilité technique de créer un wallet cryptographique avant certification, si c'est une décision économique/UX souhaitée.

Dans ce cas il faut nommer clairement les états :

```text
WALLET_CREATED
    ↓
BIOMETRIC_PENDING
    ↓
HUMAN_PROOFED
    ↓
NODE_ELIGIBLE
    ↓
CERTIFICATION_PENDING
    ↓
VERIFIED_100
    ↓
REWARD_TRANSFERABLE
```

---

# 6. Le point le plus important : empreinte digitale ≠ DeviceID

C'est actuellement une des grosses failles conceptuelles du dépôt.

Le système possède déjà un `DeviceRegistry`.

Il stocke notamment :

```text
device_id
fingerprint
human_id
```

mais son propre code précise que le `fingerprint` est un **hash d'identification du périphérique**, pas une empreinte biométrique humaine.

Donc actuellement :

```text
Device A
   ↓
DeviceID A
   ↓
Wallet A
```

et

```text
Device B
   ↓
DeviceID B
   ↓
Wallet B
```

ne permettent absolument pas de conclure :

```text
même humain
```

---

# 7. Ton exigence "même doigt sur un autre téléphone" est beaucoup plus difficile

Tu demandes :

```text
empreinte X → Wallet A

même empreinte X
    ↓
autre téléphone
    ↓
autre navigateur
    ↓
autre PC
    ↓
création Wallet B
```

et tu veux :

```text
REJECT
```

C'est bien la bonne propriété fonctionnelle.

Mais il faut être extrêmement précis techniquement.

Le WebAuthn actuel ne donne pas simplement au serveur :

```text
"voici l'empreinte digitale de l'utilisateur"
```

Le mécanisme courant est plutôt :

```text
doigt
 ↓
capteur/OS
 ↓
déverrouillage de l'authentificateur
 ↓
clé privée du credential WebAuthn
 ↓
signature d'un challenge
 ↓
serveur
```

Le serveur reçoit une **preuve cryptographique**, pas le modèle biométrique brut.

Le code actuel le reconnaît d'ailleurs explicitement : `webauthn_fingerprint` prouve actuellement la possession de l'appareil inscrit + la vérification utilisateur par l'OS, mais **ne prouve pas qu'il s'agit d'un humain unique mondialement**.

Donc il serait dangereux de simplement dire :

> "On va hasher l'empreinte et la mettre dans la blockchain."

Ce n'est pas automatiquement réalisable avec WebAuthn.

---

# 8. Je déconseille absolument de graver l'empreinte biométrique brute dans la blockchain

Ton objectif est bon :

> pouvoir empêcher qu'une même biométrie crée plusieurs wallets.

Mais la solution ne doit pas être :

```text
empreinte brute
      ↓
blockchain
```

Une blockchain est précisément un endroit où une donnée peut devenir extrêmement difficile à retirer.

Il faut conserver le principe déjà présent dans ARTCB :

```text
biométrie brute
      ↓
reste localement protégée
      ↓
preuve cryptographique / attestation
      ↓
ARTCB
```

Le dépôt actuel indique d'ailleurs explicitement que les données biométriques brutes ne sont pas stockées.

---

# 9. Architecture que je recommande pour ton objectif

Le modèle cible devient :

```text
                 ┌──────────────────────┐
                 │       HUMAIN         │
                 └──────────┬───────────┘
                            │
                       empreinte
                            │
                            ▼
                 ┌──────────────────────┐
                 │   HUMAN PROOF        │
                 │ preuve biométrique   │
                 └──────────┬───────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   HumanID    │
                    └──────┬───────┘
                           │
                 ┌─────────┴──────────┐
                 │                    │
                 ▼                    ▼
             WalletID              DeviceID
                 │                    │
                 │                    │
                 └────────┬───────────┘
                          │
                          ▼
                     Node binding
                          │
                          ▼
                  Certification Q=100
                          │
             ┌────────────┴────────────┐
             │                         │
        Validator 1                Validator 100
             │                         │
             └────────────┬────────────┘
                          ▼
                    VERIFIED_100
                          │
                          ▼
                 récompense libérée
                          │
                          ▼
                    transfert permis
```

Et surtout :

```text
DeviceID ≠ HumanID
WalletID ≠ HumanID
HumanID = identité humaine
```

Un humain pourra avoir :

```text
HumanID H1
   │
   ├── Wallet W1
   │
   ├── téléphone T1
   ├── PC P1
   └── navigateur B1
```

mais **jamais** :

```text
HumanID H1
   ├── Wallet W1
   └── Wallet W2
```

---

# 10. Ton nouveau contrôle anti-double-wallet

La règle doit devenir une contrainte protocolaire.

### À la certification biométrique

```text
BiometricProof
       ↓
résolution HumanID
       ↓
chercher HumanID dans registre mondial
       ↓
HumanID possède déjà WalletID ?
       │
       ├── OUI → REJECT
       │
       └── NON → continuer
```

Puis :

```text
HumanID H123
WalletID W123
```

est définitivement associé.

Une nouvelle tentative :

```text
empreinte → H123
nouveau wallet → W999
```

donne :

```text
H123 already owns W123
       ↓
W999 impossible
```

Et ceci doit fonctionner indépendamment de :

* téléphone ;
* navigateur ;
* ordinateur ;
* IP ;
* DeviceID ;
* installation du node.

**C'est exactement le changement conceptuel nécessaire : la contrainte ne doit plus être `one device → one wallet`, mais `one HumanID → one WalletID`.**

---

# 11. Le node

Ton idée :

> wallet sans empreinte = impossible de lier un node.

Je la valide comme règle d'architecture.

Donc :

```text
Installation node
      ↓
demande WalletID
      ↓
preuve de possession du wallet
      ↓
preuve HumanID
      ↓
vérification :
    wallet existe ?
    human existe ?
    biometric proof existe ?
    wallet appartient à HumanID ?
      ↓
OUI
      ↓
NodeID ↔ HumanID ↔ WalletID
```

Sinon :

```text
wallet sans Human Proof
      ↓
NODE_BINDING_DENIED
```

---

# 12. Mais je corrige une chose dans ta procédure de clé privée

Tu proposes :

> installation demande la clé publique et la clé privée.

**Je ne recommande pas que la clé privée soit saisie ou envoyée au serveur.**

La clé privée doit rester secrète.

Le processus sécurisé doit être :

```text
installation
     ↓
clé publique du wallet
     ↓
challenge signé localement avec clé privée
     ↓
signature
     ↓
ARTCB vérifie avec clé publique
```

Donc le système prouve :

> cette installation possède effectivement la clé privée correspondant à cette adresse.

Sans que la clé privée quitte la machine.

C'est beaucoup plus sûr que :

```text
clé privée → serveur
```

ou :

```text
clé privée → API
```

La clé privée ne devrait jamais devenir une donnée réseau ordinaire.

---

# 13. Ce que le node doit réellement demander

Je définirais donc le protocole comme :

```text
ARTCB NODE INSTALLATION

1. Wallet address / public key
2. HumanID
3. Human biometric proof
4. Wallet ownership challenge
5. Signature locale du challenge
6. NodeID
7. association HumanID ↔ WalletID ↔ NodeID
```

La clé privée sert à **signer**, pas à être transmise.

---

# 14. Et ensuite viennent les récompenses

Tu proposes une distinction très intéressante :

### Utilisation de base

```text
Human Proof
+
Wallet
+
Node
```

permet :

```text
utiliser ARTCB
faire fonctionner un node
participer au réseau
```

mais :

```text
récompense non transférable
```

jusqu'à certification.

### Certification

```text
Human Proof
      ↓
demande certification
      ↓
sélection aléatoire des validateurs
      ↓
100 validations humaines distinctes
      ↓
anti-collusion
      ↓
100/100
      ↓
CERTIFIED
      ↓
récompenses transférables
```

C'est beaucoup plus clair.

---

# 15. La sélection des 100 validateurs doit elle aussi être réellement aléatoire

Tu demandes :

> 100 validateurs aléatoires disponibles en ligne.

Il faut éviter :

```text
prendre les 100 premiers
```

ou :

```text
prendre les 100 mêmes validateurs
```

Le protocole cible devrait avoir :

```text
ValidatorPool
      ↓
validators éligibles
      ↓
seed déterministe et imprévisible
      ↓
sélection aléatoire
      ↓
100 ValidatorHumanID distincts
```

Par exemple conceptuellement :

```text
seed =
Hash(
    block_hash
    +
    HumanID candidat
    +
    certification_epoch
)
```

puis :

```text
RandomSelection(seed, eligible_validators)
```

Ce n'est ici **qu'une proposition d'architecture**, pas quelque chose que je prétends déjà présent dans le dépôt.

---

# 16. Chaque validation doit avoir une identité

C'est probablement le correctif le plus important à apporter au système Q=100.

Aujourd'hui :

```text
add_finder_validation(human_id)
```

ne dit pas :

```text
QUI valide ?
```

Le protocole cible doit plutôt conceptuellement enregistrer quelque chose comme :

```text
CandidateHumanID
ValidatorHumanID
CertificationID
Decision
Timestamp
Signature
```

et imposer :

```text
ValidatorHumanID unique
```

Donc :

```text
Validator A → ACCEPT
Validator A → ACCEPT
Validator A → ACCEPT
...
```

ne doit compter que :

```text
1 validation
```

et non 100.

---

# 17. Il faut aussi empêcher qu'un validateur valide son propre dossier

Règle :

```text
CandidateHumanID == ValidatorHumanID
            ↓
           DENY
```

Et il faut aller plus loin :

```text
même HumanID
même wallet
même organisation conflictuelle
même groupe interdit
relations suspectes
```

→ exclusion selon les règles anti-collusion.

---

# 18. Le seuil de certification doit donc devenir

Je propose de considérer comme invariant :

```text
CERTIFICATION_ELIGIBLE =
    wallet_exists
    AND human_proof_valid
    AND wallet_bound_to_human
    AND no_existing_wallet_for_human
```

Puis :

```text
CERTIFICATION_COMPLETE =
    100 distinct eligible validators
    AND valid signatures
    AND no duplicate validator
    AND no self-validation
    AND anti-collusion checks pass
```

Puis seulement :

```text
REWARD_TRANSFERABLE = true
```

---

# 19. Ce que je retrouve actuellement concernant le facial

Ici ton constat est confirmé.

Le facial n'est **pas supprimé** actuellement.

Le backend possède encore :

```text
webauthn_face
face_camera
face/enroll
face/login
```

et le frontend possède toujours le parcours `RegisterBiometric`.

Le rapport 215 avait seulement corrigé la terminologie pour parler de **« présence faciale locale »** plutôt que de « reconnaissance faciale ».

Le code actuel contient encore explicitement les modalités face.

Donc :

> **Le facial n'est actuellement ni supprimé, ni réellement désactivé de toute la chaîne.**

Et aucun changement n'a été fait aujourd'hui.

---

# 20. Si on retire le facial, il ne faudra surtout pas seulement cacher le bouton

Il faudra rechercher et éliminer les dépendances de :

```text
UI
 ↓
frontend state
 ↓
routes API
 ↓
WebAuthn modality
 ↓
face_camera
 ↓
face storage
 ↓
auth_methods
 ↓
tests
 ↓
audit logs
 ↓
configuration
 ↓
documentation
 ↓
simulations
 ↓
certification/assurance
```

Sinon on aura :

```text
UI cachée
mais API face encore active
```

ce qui serait une **fausse suppression**.

---

# 21. État cible que je verrouillerais

### Identité

```text
1 humain
    ↓
1 HumanID
    ↓
1 WalletID maximum
```

### Machines

```text
1 HumanID
    ↓
N DeviceID
```

Donc plusieurs machines sont permises.

### Node

```text
Wallet
+
Human Proof
+
wallet ownership signature
        ↓
Node binding autorisé
```

### Sans empreinte

```text
Wallet
    ↓
pas de Human Proof
    ↓
pas de Node binding
```

### Certification

```text
Human Proof
    ↓
Certification Request
    ↓
100 validateurs humains distincts
    ↓
sélection aléatoire
    ↓
anti-Sybil
    ↓
anti-collusion
    ↓
100 validations
    ↓
CERTIFIED
```

### Argent

```text
PoL reward
     ↓
accumulée/réservée
     ↓
NON TRANSFÉRABLE
     ↓
100/100
     ↓
TRANSFERABLE
```

---

# 22. Les questions que le protocole doit absolument résoudre

Voici les points que je considère maintenant comme **questions de conception obligatoires**, et non comme détails secondaires.

### A. Biométrie

1. Comment obtient-on une preuve biométrique utilisable mondialement ?
2. Comment reconnaît-on le même humain sur deux appareils différents ?
3. Comment empêche-t-on un même doigt d'obtenir deux HumanID ?
4. Que se passe-t-il si deux capteurs produisent des preuves différentes pour le même doigt ?
5. Que se passe-t-il après changement de téléphone ?
6. Que se passe-t-il après perte du téléphone ?
7. Peut-on ré-enregistrer un doigt ?
8. Que se passe-t-il si le capteur biométrique est compromis ?
9. Comment révoque-t-on une preuve compromise ?
10. Peut-on avoir plusieurs doigts pour le même HumanID ?

### B. Wallet

11. Un wallet sans biométrie peut-il recevoir des fonds ?
12. Peut-il produire des récompenses ?
13. Peut-il transférer ?
14. Peut-il installer un node ?
15. Peut-il demander certification ?

### C. Node

16. La clé privée reste-t-elle toujours locale ?
17. Comment signe-t-on le challenge d'installation ?
18. Comment le serveur vérifie-t-il l'association ?
19. Peut-on déplacer un node vers une autre machine ?
20. Combien de nodes un HumanID peut-il posséder ?

### D. Q=100

21. Comment sélectionne-t-on les 100 validateurs ?
22. Comment garantit-on qu'ils sont 100 **humains distincts** ?
23. Comment empêche-t-on un validateur de voter deux fois ?
24. Comment empêche-t-on l'auto-validation ?
25. Comment détecte-t-on les collusions ?
26. Que se passe-t-il si seulement 73 validateurs sont online ?
27. Que se passe-t-il si un validateur disparaît pendant le processus ?
28. Quel est le timeout ?
29. Faut-il remplacer un validateur défaillant ?
30. Le remplacement doit-il être aléatoire également ?
31. Quelle preuve cryptographique est conservée pour chaque validation ?
32. Comment un autre node peut-il vérifier le `100/100` ?

### E. Récompenses

33. Où sont stockées les récompenses avant certification ?
34. Comment le protocole empêche-t-il leur transfert prématuré ?
35. Que se passe-t-il si la certification échoue ?
36. Que se passe-t-il si elle est suspendue après 100/100 ?
37. Peut-on retirer une certification ?
38. Comment traiter un humain dont l'identité est contestée ?

---

# 23. Et il reste plusieurs anciennes failles que je ne vais pas laisser disparaître de la liste

Même si nous recentrons maintenant le chantier sur :

**empreinte digitale → HumanID → wallet unique → node → Q=100**, les anciens travaux restent ouverts en parallèle.

Notamment :

* preuve réelle `USER ↔ WALLET` ;
* preuve réelle `USER ↔ NODE` multi-nœuds ;
* `UNIQUE_HUMAN` actuellement non démontré ;
* certification réellement distribuée `100/100` ;
* sélection aléatoire vérifiable ;
* validations distinctes cryptographiquement identifiables ;
* récupération/perte wallet ;
* révocation d'identité ;
* changement de device ;
* conflit d'identité ;
* QR/phone pairing réel ;
* tests biométriques sur vrais appareils ;
* certification réseau C0–C6 ;
* failover réel ;
* preuves distribuées reproductibles ;
* Nakamoto coefficient ;
* ORG/KYB complet ;
* nomination réelle des validateurs d'organisation ;
* séparation Creator / Validator ;
* contrôle anti-collusion ;
* etc.

Le rapport R352 conserve notamment `CERTIFIED_100 = false`. Le fait que la règle Q=100 soit historiquement validée **ne signifie donc pas que le réseau est actuellement certifié 100/100**.

---

# 24. Conclusion de l'audit actuel

Je considère maintenant le modèle cible comme suit :

```text
                 WALLET
                    │
                    ▼
           EMPREINTE DIGITALE
                    │
                    ▼
               HUMAN PROOF
                    │
                    ▼
                 HumanID
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
       WalletID             DeviceID
          │                   │
          └─────────┬─────────┘
                    ▼
                NodeID
                    │
                    ▼
          CERTIFICATION REQUEST
                    │
                    ▼
        100 VALIDATEURS DISTINCTS
                    │
             anti-Sybil
             anti-collusion
             anti-duplicate
                    │
                    ▼
                 100/100
                    │
                    ▼
          REWARD TRANSFERABLE
```

Et la règle fondamentale devient :

> **Le DeviceID identifie une installation. Le WalletID identifie le portefeuille. Le HumanID identifie l'humain. La biométrie est la porte permettant d'établir le HumanID. Le wallet ne peut être lié à un node que lorsque cette preuve humaine existe. Et une même identité humaine ne peut posséder qu'un seul wallet.**

### Mais deux points doivent rester explicitement ouverts

**1. Le WebAuthn fingerprint actuel ne fournit pas encore cette unicité humaine mondiale.** Le dépôt le reconnaît lui-même : son niveau actuel est 2 et `unique_human_proven=false`.

**2. Le code Q=100 actuel compte des validations mais ne lie pas chaque validation à un `ValidatorHumanID` distinct.** Donc il faut conserver la décision historique Q=100, mais considérer l'implémentation actuelle comme **incomplète pour l'exigence "100 personnes humaines différentes"**.

Enfin, **aucune modification GitHub n'a été réalisée** dans cet audit.
