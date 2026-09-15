Oui. Après remise à jour sur le dépôt `main` de [`vgactech/artcb`](https://github.com/vgactech/artcb/tree/main?utm_source=chatgpt.com), **je recommande de formaliser ce que tu proposes comme un véritable “Test Wallet / Test Identity Domain”**, et non comme un simple contournement de la validation.

Le besoin est pertinent parce que le code actuel impose effectivement la contrainte d’un wallet par empreinte client : `POST /wallet/create` appelle `check_and_bind()`, et le mécanisme existant prévoit `ARTCB_ALLOW_MULTI_WALLET=true` pour les tests/dev.   Le rapport antérieur confirme également que le deuxième wallet sur une même empreinte provoque normalement un `409`, tandis que `ARTCB_ALLOW_MULTI_WALLET=true` contourne cette contrainte.

Mais **je ne recommande pas de continuer à multiplier les exceptions `ALLOW_MULTI_WALLET`**.

# 1. Le concept que je recommande

Créer deux domaines cryptographiques explicitement séparés :

```text
                    ARTCB
                      │
          ┌───────────┴───────────┐
          │                       │
       PROD                    TEST
       ARTCB                    ARTCBDEV
          │                       │
   vrais wallets            wallets de test
   vraies identités         identités synthétiques
   vraies attestations      attestations simulées
   vraie économie           économie de test
   vrais Genesis            Genesis de test
```

Le wallet de test doit être **un vrai wallet au niveau du protocole**, avec :

* vraie paire de clés ;
* vraie signature ;
* vraie adresse ;
* vrais nonces ;
* vraies transactions ;
* vraies validations ;
* vraies règles de permissions ;
* vraie logique PoL ;
* vrais agents ;
* vrais ORG/GROUP ;
* vrais blocs ;
* vrais Genesis de test ;
* vraie vérification cryptographique.

La seule différence fondamentale est :

> **l'identité et les attestations utilisées pour les tests peuvent être synthétiques, et le domaine cryptographique est différent de celui du réseau réel.**

C'est beaucoup plus propre que :

```text
wallet normal
    ↓
validation obligatoire
    ↓
ARTCB_ALLOW_MULTI_WALLET=true
    ↓
on laisse passer
```

---

# 2. `artcbdev...` est une bonne idée, mais le préfixe ne suffit absolument pas

Ton idée :

```text
ARTCBDEV...
```

est bonne pour rendre visuellement le wallet identifiable.

Mais **il ne faut jamais simplement modifier le texte affiché**.

Il faut que `ARTCBDEV` provienne d'une **séparation cryptographique réelle**.

Par exemple, conceptuellement :

```text
PRODUCTION

WalletID =
H("ARTCB/WALLET/MAINNET/V1" || public_key)
```

et :

```text
TEST

WalletID =
H("ARTCB/WALLET/TEST/V1" || public_key)
```

Ainsi :

```text
même clé privée
       │
       ├── domaine MAINNET → wallet ARTCB...
       │
       └── domaine TEST    → wallet ARTCBDEV...
```

Les deux identités seraient cryptographiquement différentes.

Et surtout, je recommande que **la séparation existe aussi au niveau des signatures**.

Par exemple :

```text
TransactionHash =
H(
    NetworkID
    || WalletDomain
    || WalletID
    || Nonce
    || Payload
)
```

Donc une signature faite dans :

```text
ARTCBDEV
```

ne doit pas devenir valide sur :

```text
ARTCB MAINNET
```

C'est la protection contre le **replay inter-réseaux**.

C'est-à-dire :

> empêcher quelqu'un de prendre une transaction parfaitement valide sur le réseau de test et de la rejouer sur le vrai réseau.

---

# 3. Le point le plus important : le wallet de test doit conserver les validations

Je modifierais donc légèrement ton idée.

Tu dis :

> « wallet de test qui contient toutes les validations actives »

**Oui. Exactement.**

Mais il faut faire :

```text
TEST
 │
 ├── validation cryptographique      ACTIVE
 ├── validation clé privée           ACTIVE
 ├── validation signature            ACTIVE
 ├── validation nonce                ACTIVE
 ├── validation anti-replay           ACTIVE
 ├── validation device               ACTIVE
 ├── validation identité             ACTIVE
 ├── validation attestation          ACTIVE
 ├── validation certificat            ACTIVE
 ├── validation validateurs           ACTIVE
 ├── validation quorum                ACTIVE
 ├── validation permissions           ACTIVE
 ├── validation agent                ACTIVE
 ├── validation PoL                  ACTIVE
 ├── validation ORG                  ACTIVE
 ├── validation GROUP                ACTIVE
 ├── validation Genesis              ACTIVE
 └── validation consensus             ACTIVE
```

Ce qui change n'est **pas le moteur de validation**.

Ce qui change est la **source des preuves**.

---

# 4. Il faut séparer « validation » et « preuve »

C'est probablement le point architectural le plus important de toute la proposition.

Prenons :

```text
Validation biométrique
```

Le moteur doit continuer à faire :

```text
preuve reçue
     ↓
signature correcte ?
     ↓
format correct ?
     ↓
identité correspondante ?
     ↓
expiration ?
     ↓
révocation ?
     ↓
niveau requis ?
     ↓
VALID / REJECT
```

Sur un vrai wallet :

```text
preuve = vraie preuve biométrique / matérielle
```

Sur un wallet de test :

```text
preuve = TestAttestation
```

Mais **le moteur de validation reste le même**.

Donc :

```text
                   VALIDATOR ENGINE
                         │
              ┌──────────┴──────────┐
              │                     │
          PRODUCTION              TEST
              │                     │
      RealAttestation        TestAttestation
```

Cela permet de tester le comportement réel sans devoir faire une biométrie réelle à chaque création de wallet.

---

# 5. Je recommande surtout un système de PHASES

Tu as donné :

> wallet + empreinte valide
> wallet + empreinte valide + 10 % certifié
> wallet + empreinte valide + 100 % certifié

C'est exactement ce qu'il faut formaliser.

Mais je ne ferais **pas** du `10 % / 100 %` une simple variable.

Je créerais un **état de validation explicite**.

## Proposition

| Phase | État                | Signification                                     |
| ----- | ------------------- | ------------------------------------------------- |
| P0    | `KEY_ONLY`          | clé privée + clé publique uniquement              |
| P1    | `DEVICE_BOUND`      | empreinte appareil validée                        |
| P2    | `IDENTITY_BOUND`    | identité associée                                 |
| P3    | `IDENTITY_ATTESTED` | attestation d'identité valide                     |
| P4    | `CERTIFICATION_10`  | premier niveau de certification                   |
| P5    | `CERTIFICATION_25`  | 25 % des validateurs requis                       |
| P6    | `CERTIFICATION_50`  | moitié du quorum                                  |
| P7    | `CERTIFICATION_75`  | 75 %                                              |
| P8    | `CERTIFICATION_100` | quorum complet                                    |
| P9    | `ACTIVE`            | wallet pleinement actif                           |
| P10   | `MATURE`            | wallet ayant satisfait les conditions de maturité |
| PX    | `EXPIRED`           | certification expirée                             |
| PR    | `REVOKED`           | identité/certification révoquée                   |
| PS    | `SUSPENDED`         | temporairement suspendu                           |
| PRC   | `RECOVERY`          | procédure de récupération                         |
| PRT   | `ROTATION_PENDING`  | changement de clé en cours                        |
| PRF   | `ROTATED`           | nouvelle clé activée                              |

Cela devient alors un **automate d'état**.

C'est-à-dire que le wallet ne peut pas simplement dire :

```json
{
  "certification": 100
}
```

Il doit avoir un historique cohérent :

```text
KEY_ONLY
   ↓
DEVICE_BOUND
   ↓
IDENTITY_BOUND
   ↓
IDENTITY_ATTESTED
   ↓
CERTIFICATION_10
   ↓
CERTIFICATION_25
   ↓
CERTIFICATION_50
   ↓
CERTIFICATION_75
   ↓
CERTIFICATION_100
   ↓
ACTIVE
```

---

# 6. Et il faut pouvoir tester les transitions incorrectes

C'est indispensable.

Par exemple :

```text
KEY_ONLY
   ↓
CERTIFICATION_100
```

**REJECT**

Pourquoi ?

Parce qu'il manque :

```text
DEVICE_BOUND
IDENTITY_BOUND
IDENTITY_ATTESTED
```

Même chose :

```text
CERTIFICATION_50
   ↓
ACTIVE
```

doit être refusé si le protocole exige 100 %.

Et :

```text
REVOKED
   ↓
ACTIVE
```

doit être impossible sans procédure de réactivation autorisée.

C'est justement ce genre de test qui permettra de savoir si le protocole fonctionne réellement.

---

# 7. Il faut aussi tester les validateurs individuellement

Ton idée « 10 % certifié » doit être améliorée.

Je recommande de stocker **les validateurs eux-mêmes**, pas seulement un pourcentage.

Exemple :

```json
{
  "required_validators": 100,
  "certifications": [
    "validator_001",
    "validator_002",
    "validator_003"
  ],
  "certified_count": 10,
  "certification_percent": 10
}
```

Parce que :

```text
10 %
```

ne dit pas :

> **qui** a certifié.

Alors que le protocole doit pouvoir vérifier :

```text
Validator #1 → VALID
Validator #2 → VALID
Validator #3 → REVOKED
Validator #4 → INVALID
...
```

Donc le vrai calcul devient :

```text
certification_percent =
valid_unique_certifiers
/
required_validators
× 100
```

---

# 8. Et attention au mot « 100 % »

Il y a une ambiguïté importante.

Supposons :

```text
100 validateurs enregistrés
```

et :

```text
73 répondent
```

Que signifie :

```text
100 %
```

?

Cela peut vouloir dire :

### A — 100 % des validateurs actifs

```text
73 / 73 = 100 %
```

ou :

### B — 100 % du quorum requis

```text
73 / 100 = 73 %
```

ou :

### C — 100 validateurs ont individuellement certifié

```text
100 / 100 = 100 %
```

Ces trois définitions sont complètement différentes.

**Je recommande B ou C selon la règle économique du protocole, mais elle doit être explicitement inscrite dans le modèle.**

---

# 9. Je rajouterais plusieurs phases que tu n'as pas citées

Il manque notamment :

### `KEY_ONLY`

Permet de tester :

```text
clé privée
clé publique
signature
adresse
```

sans identité.

---

### `DEVICE_BOUND`

Permet de tester :

```text
wallet
+
empreinte appareil
```

C'est particulièrement important parce que le dépôt actuel possède déjà cette logique de liaison wallet/device.

---

### `IDENTITY_BOUND`

Le wallet possède une identité, mais elle n'est pas encore totalement certifiée.

---

### `ATTESTATION_VALID`

La preuve cryptographique de l'identité est valide.

---

### `CERTIFICATION_PARTIAL`

Exemple :

```text
10 %
25 %
50 %
75 %
```

Très utile pour tester les seuils.

---

### `CERTIFICATION_COMPLETE`

```text
100 %
```

---

### `ACTIVE`

Toutes les conditions nécessaires à l'utilisation normale sont remplies.

---

### `MATURE`

Très intéressant pour ton projet si certaines fonctions économiques exigent une ancienneté ou une stabilité minimale.

---

### `EXPIRED`

Permet de tester :

```text
certificat expiré
```

---

### `REVOKED`

Permet de tester :

```text
wallet révoqué
```

---

### `SUSPENDED`

Permet de tester :

```text
suspension temporaire
```

---

### `RECOVERY`

Permet de tester les procédures de récupération.

---

### `KEY_ROTATION`

Très important.

On doit pouvoir tester :

```text
clé privée A
     ↓
rotation
     ↓
clé privée B
```

sans perdre :

```text
identité
certifications
permissions
historique
```

---

# 10. Je créerais donc plusieurs familles de clés de test

Pas un seul wallet de test.

Je recommande :

```text
ARTCBDEV-KEY-001
ARTCBDEV-KEY-002
ARTCBDEV-KEY-003
...
```

Mais surtout avec des profils.

### Profil A — wallet minimal

```text
KEY_ONLY
```

### Profil B — wallet device

```text
KEY
+
DEVICE
```

### Profil C — identité valide

```text
KEY
+
DEVICE
+
IDENTITY
```

### Profil D — certification 10 %

```text
KEY
+
DEVICE
+
IDENTITY
+
10 validators
```

### Profil E — certification 50 %

```text
...
+
50 validators
```

### Profil F — certification complète

```text
...
+
100 validators
```

### Profil G — wallet expiré

```text
EXPIRED
```

### Profil H — wallet révoqué

```text
REVOKED
```

### Profil I — wallet attaqué

```text
mauvaise signature
```

### Profil J — wallet replay

```text
nonce déjà utilisé
```

---

# 11. Et je rajouterais des wallets volontairement « mauvais »

C'est extrêmement important pour un vrai audit.

Il faut pouvoir fabriquer automatiquement :

```text
TEST_VALID
TEST_BAD_SIGNATURE
TEST_WRONG_PRIVATE_KEY
TEST_WRONG_PUBLIC_KEY
TEST_WRONG_DEVICE
TEST_EXPIRED
TEST_REVOKED
TEST_REPLAY
TEST_WRONG_NONCE
TEST_WRONG_VALIDATOR
TEST_DUPLICATE_VALIDATOR
TEST_INSUFFICIENT_QUORUM
TEST_WRONG_NETWORK
TEST_WRONG_GENESIS
TEST_WRONG_DOMAIN
TEST_UNAUTHORIZED_AGENT
```

Ainsi le test devient :

```text
entrée
  ↓
validation
  ↓
PASS / REJECT
  ↓
raison exacte
```

Et non :

```text
test wallet → tout passe
```

---

# 12. Le wallet de test doit pouvoir aller jusqu'à PoL / ORG / GROUP / Agent

Je considère cela comme **obligatoire** si l'objectif est de remplacer la création répétitive de wallets réels.

Sinon tu vas gagner du temps uniquement au niveau :

```text
création wallet
```

mais tu seras encore obligé de créer de vrais wallets pour tester :

```text
wallet
 ↓
identity
 ↓
ORG
 ↓
GROUP
 ↓
agent
 ↓
PoL
 ↓
transaction
 ↓
reward
 ↓
bloc
```

Je recommande donc :

```text
ARTCBDEV wallet
       │
       ├── identity
       ├── device
       ├── validators
       ├── ORG
       ├── GROUP
       ├── agent
       ├── PoL
       ├── transactions
       ├── balances TEST
       └── Genesis TEST
```

---

# 13. Très important : l'économie de test doit être séparée

Je ne veux surtout pas :

```text
ARTCBDEV wallet
       ↓
balance réelle ARTCB
```

Il faut :

```text
ARTCBDEV
   ↓
TEST ASSET
```

et :

```text
ARTCB MAINNET
   ↓
REAL ASSET
```

avec une règle dure :

```text
TEST → MAINNET = REJECT
MAINNET → TEST = REJECT
```

sauf mécanisme de bridge explicitement conçu et sécurisé.

---

# 14. Le Genesis de test doit également être différent

Je recommande :

```text
MAINNET
Genesis_Main
```

et :

```text
TEST
Genesis_Test
```

avec notamment :

```text
network_id
chain/domain id
genesis hash
protocol version
validation policy
asset domain
```

Cela donne :

```text
              Genesis
                 │
        ┌────────┴────────┐
        │                 │
      MAIN              TEST
        │                 │
  ARTCB Main         ARTCBDEV
```

Cela évite qu'un nœud puisse confondre les deux univers.

---

# 15. Le plus gros piège à éviter

Il ne faut surtout pas faire :

```python
if wallet.is_test:
    skip_validation()
```

C'est précisément **ce que je veux éviter**.

Il faut faire :

```python
validation_context = TEST
```

puis :

```text
même validation
       │
       ├── production policy
       │
       └── test policy
```

Par exemple :

```text
validate_signature()
        ↓
validate_device()
        ↓
validate_identity()
        ↓
validate_attestation()
        ↓
validate_quorum()
        ↓
validate_permissions()
```

Toutes ces fonctions restent exécutées.

---

# 16. Le système actuel `ARTCB_ALLOW_MULTI_WALLET` devient alors secondaire

Actuellement, le dépôt possède déjà cette possibilité pour les tests/dev. Le rapport précédent la documente explicitement.

Je ne supprimerais pas immédiatement ce mécanisme.

Je ferais plutôt :

```text
Phase actuelle
ARTCB_ALLOW_MULTI_WALLET
        ↓
compatibilité tests existants
```

puis :

```text
Nouvelle architecture
ARTCBDEV / TEST DOMAIN
        ↓
vrai mécanisme de test
```

et progressivement :

```text
ALLOW_MULTI_WALLET
        ↓
legacy / dev only
```

Parce que sinon tu risques de conserver deux systèmes de test concurrents.

---

# 17. Une amélioration supplémentaire : profil de test déclaratif

Je recommande quelque chose comme :

```yaml
wallet:
  domain: test
  profile: certification_50

identity:
  type: synthetic
  valid: true

device:
  bound: true
  valid: true

certification:
  validators_required: 100
  validators_valid: 50

crypto:
  signature: valid

nonce:
  valid: true
```

Et pour un autre test :

```yaml
wallet:
  domain: test
  profile: certification_50

identity:
  type: synthetic
  valid: true

device:
  bound: true
  valid: true

certification:
  validators_required: 100
  validators_valid: 49
```

Résultat attendu :

```text
CERTIFICATION_50 → REJECT
```

Cela permettrait à Cursor/aux agents de générer des centaines de scénarios automatiquement.

---

# 18. Je recommande même un `Test Wallet Factory`

Architecture :

```text
TestWalletFactory
       │
       ├── create(KEY_ONLY)
       ├── create(DEVICE_BOUND)
       ├── create(IDENTITY_VALID)
       ├── create(CERT_10)
       ├── create(CERT_25)
       ├── create(CERT_50)
       ├── create(CERT_75)
       ├── create(CERT_100)
       ├── create(EXPIRED)
       ├── create(REVOKED)
       ├── create(WRONG_DEVICE)
       ├── create(REPLAY)
       └── create(WRONG_DOMAIN)
```

Le test pourrait alors demander :

```text
Créer 20 wallets :
5 × KEY_ONLY
5 × DEVICE_BOUND
5 × CERT_50
5 × CERT_100
```

et obtenir exactement les objets nécessaires.

---

# 19. Il faut aussi pouvoir changer de phase volontairement

Un autre point que je considère essentiel :

**ne pas recréer la clé à chaque phase.**

Exemple :

```text
Wallet DEV-001

P0 KEY_ONLY
       ↓
P1 DEVICE_BOUND
       ↓
P2 IDENTITY_BOUND
       ↓
P3 ATTESTED
       ↓
P4 CERT_10
       ↓
P5 CERT_50
       ↓
P6 CERT_100
       ↓
P7 ACTIVE
```

Cela permet de tester le véritable comportement du protocole.

On peut alors vérifier :

```text
Que devient le wallet ?
Que deviennent ses permissions ?
Que devient son historique ?
Que deviennent ses certifications ?
Que devient son nonce ?
Que deviennent ses agents ?
Que devient son solde ?
```

C'est beaucoup plus intéressant qu'une succession de wallets artificiels.

---

# 20. Et il faut conserver l'historique des validations

Je recommande fortement :

```json
{
  "wallet_id": "ARTCBDEV...",
  "state": "CERTIFICATION_50",
  "history": [
    {
      "state": "KEY_ONLY",
      "timestamp": "...",
      "event": "CREATED"
    },
    {
      "state": "DEVICE_BOUND",
      "timestamp": "...",
      "event": "DEVICE_VALIDATED"
    },
    {
      "state": "IDENTITY_BOUND",
      "timestamp": "...",
      "event": "IDENTITY_VALIDATED"
    },
    {
      "state": "CERTIFICATION_10",
      "timestamp": "...",
      "event": "QUORUM_REACHED"
    },
    {
      "state": "CERTIFICATION_50",
      "timestamp": "...",
      "event": "QUORUM_REACHED"
    }
  ]
}
```

Cela permettra ensuite de prouver :

> pourquoi ce wallet est actuellement dans cet état.

---

# 21. Une distinction supplémentaire que je veux absolument introduire

Il faut séparer :

```text
CERTIFICATION LEVEL
```

et :

```text
AUTHORIZATION LEVEL
```

Ce n'est pas nécessairement la même chose.

Par exemple :

```text
100 % certifié
```

ne signifie pas forcément :

```text
administrateur
```

Un wallet pourrait être :

```text
CERTIFICATION = 100 %
AUTHORIZATION = USER
```

ou :

```text
CERTIFICATION = 100 %
AUTHORIZATION = VALIDATOR
```

ou :

```text
CERTIFICATION = 100 %
AUTHORIZATION = AGENT
```

Cela évite une escalade de privilèges.

---

# 22. Modèle final que je recommande

Je verrais donc le modèle ainsi :

```text
                    ARTCB WALLET
                         │
              ┌──────────┴──────────┐
              │                     │
            MAIN                  TEST
          ARTCB...             ARTCBDEV...
              │                     │
              │                     │
       Real Identity          Test Identity
              │                     │
       Real Attestation       Synthetic Attestation
              │                     │
              └──────────┬──────────┘
                         │
                 SAME VALIDATORS
                         │
              ┌──────────┴──────────┐
              │                     │
        Crypto Validation      Identity Validation
              │                     │
        Device Validation      Certification
              │                     │
              └──────────┬──────────┘
                         │
                     QUORUM
                         │
       ┌──────┬──────┬──────┬──────┬──────┐
       │      │      │      │      │      │
      10%    25%    50%    75%   100%   ACTIVE
       │      │      │      │      │      │
       └──────┴──────┴──────┴──────┴──────┘
                         │
                  ORG / GROUP / AGENT
                         │
                        PoL
                         │
                    TEST ECONOMY
```

# 23. Ma recommandation finale

**Oui au concept. Je le considère même comme une amélioration structurante du système de test ARTCB.**

Mais je modifierais la formulation initiale :

> ❌ « un wallet qui n'a pas besoin d'être validé »

en :

> ✅ **« un wallet de domaine TEST qui possède une identité et des attestations synthétiques, mais qui traverse exactement le même pipeline de validation que le wallet réel. »**

Et j'ajouterais quatre garanties non négociables :

```text
1. ARTCBDEV ≠ ARTCB cryptographiquement
2. TEST ≠ MAINNET économiquement
3. TEST signatures ≠ MAINNET signatures
4. TEST validation ≠ validation désactivée
```

### Ce que je considère encore à vérifier dans le code avant de faire implémenter la modification

Le dépôt actuel confirme le point de blocage wallet/device et le mécanisme de test existant, mais **je ne validerais pas encore l'implémentation technique exacte du nouveau domaine sans auditer les fonctions qui calculent réellement l'identifiant/adresse du wallet, signent les transactions, construisent les Genesis et vérifient les transactions/blocs**. La recherche actuelle n'a pas suffisamment exposé ces points.

C'est la prochaine étape importante : **cartographier tous les endroits du code où `wallet_id/address`, clé publique, signature, nonce, Genesis, réseau/chaîne, PoL, récompense et permissions sont consommés**, puis déterminer exactement où introduire `TEST_DOMAIN` sans laisser une seule porte de mélange `ARTCBDEV → ARTCB`.
