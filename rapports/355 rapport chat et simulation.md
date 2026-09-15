Oui. J’ai effectué la **mise à jour directe sur `main` du dépôt GitHub `vgactech/artcb`**, puis j’ai commencé la cartographie demandée en partant des points cryptographiques, wallet, chaîne, Genesis, P2P et certification.

[Dépôt GitHub ARTCB — main](https://github.com/vgactech/artcb/tree/main?utm_source=chatgpt.com)

# 1. Résultat immédiat : le dépôt contient déjà une partie essentielle de l’architecture

Le point important est que le nouveau domaine TEST **ne doit pas être construit comme un simple `if TEST: skip_validation`**.

Le code actuel possède déjà un véritable concept de séparation de réseau avec :

* `NETWORK_ID`
* `PROTOCOL_VERSION`
* `GENESIS_HASH`
* vérification de compatibilité des pairs
* séparation `public/private ledger`
* Genesis global
* Genesis ORG/GROUP
* certification PBFT
* signatures Ed25519 / ML-DSA hybride.

La politique cryptographique actuelle définit notamment :

```text
NETWORK_ID     = artcb-mainnet-1
PROTOCOL_VERSION = 189-mainnet-1
GENESIS_HASH   = genesis-artcb-mainnet-1
```

et `accept_peer_protocol()` refuse un pair si le `network_id`, `protocol_version` ou `genesis_hash` ne correspondent pas.

**C’est extrêmement important pour notre solution : nous avons déjà le mécanisme architectural de séparation dont nous avons besoin.**

Il faut maintenant l'étendre proprement au domaine TEST.

---

# 2. Cartographie actuelle du wallet

## 2.1 Génération de l'adresse

J'ai vérifié directement :

`src/artcb/wallet/address.py`

L'adresse actuelle est calculée à partir de la clé publique Ed25519 :

```text
public_key
    ↓
SHA-256
    ↓
RIPEMD-160
    ↓
Bech32
    ↓
artcb1...
```

Le préfixe est actuellement configurable :

```python
generate_address(public_key_bytes, prefix="artcb")
```

et la vérification fait également intervenir ce préfixe :

```python
verify_address(address, prefix="artcb")
```

### Conséquence

Nous avons **déjà techniquement la possibilité** de produire :

```text
artcb1...
```

et :

```text
artcbdev1...
```

par exemple.

Mais attention :

> **changer uniquement `prefix="artcbdev"` n'est PAS suffisant pour créer un domaine cryptographiquement séparé.**

Pourquoi ?

Parce qu'actuellement :

```text
Address_MAIN = Bech32("artcb", HASH(pubkey))
Address_TEST = Bech32("artcbdev", HASH(pubkey))
```

utilisent toujours **le même hash de clé publique**.

Le préfixe protège surtout contre une erreur humaine et permet de distinguer visuellement les adresses.

Il ne constitue pas encore à lui seul une séparation de domaine cryptographique.

---

# 3. Le wallet Manager confirme également le modèle

`src/artcb/wallet/manager.py` crée actuellement :

* clé Ed25519 ;
* adresse `artcb...` ;
* éventuellement clé ML-DSA ;
* adresse hybride `artcb2...`;
* fichier de clé chiffré ;
* metadata JSON ;
* historique/balance basée sur l'adresse.

Le point particulièrement intéressant est celui-ci :

```python
address = address_from_signing_key(signing_key)
```

Donc **toute la logique d'adresse passe par un point centralisé**.

C'est une bonne situation pour introduire le domaine.

---

# 4. Ce que je recommande pour l'adresse TEST

Je ne recommande donc pas :

```text
artcbdev + même hash
```

mais plutôt :

```text
ARTCB/WALLET/MAINNET/V1
        +
public_key
        ↓
HASH
        ↓
artcb1...
```

et :

```text
ARTCB/WALLET/TEST/V1
        +
public_key
        ↓
HASH
        ↓
artcbdev1...
```

C'est-à-dire :

```text
MAIN_DOMAIN_TAG = "ARTCB/WALLET/MAINNET/V1"
TEST_DOMAIN_TAG = "ARTCB/WALLET/TEST/V1"
```

Ainsi, même si quelqu'un possède exactement la même clé publique :

```text
PUBKEY = X
```

on obtient deux identifiants cryptographiquement différents :

```text
H(MAINNET || X) != H(TEST || X)
```

### Pourquoi c'est mieux ?

Parce que le domaine devient une partie de l'identité cryptographique.

Un développeur ne peut donc pas simplement changer :

```text
artcbdev → artcb
```

pour transformer un wallet TEST en wallet MAINNET.

---

# 5. Mais il y a un problème encore plus important : la signature

J'ai vérifié le `Wallet.sign()` actuel.

Il signe directement le message :

```python
sign_hybrid(... message=message)
```

ou :

```python
self.signing_key.sign(message)
```

Donc actuellement, le domaine n'est **pas automatiquement intégré dans chaque message signé par le wallet**.

C'est le point de sécurité principal à corriger.

---

# 6. Le risque de replay TEST → MAINNET

Imagine :

```text
TEST wallet
    ↓
signe
"send 100 ARTCB"
```

Si la signature cryptographique ne contient aucune information permettant de distinguer :

```text
TEST
```

de :

```text
MAINNET
```

alors la même signature peut potentiellement être présentée à un autre validateur qui connaît la même clé publique.

C'est ce qu'on appelle un **cross-domain replay**.

### C'est-à-dire

Une opération légitime dans le réseau A est copiée dans le réseau B.

La signature est mathématiquement correcte, mais elle n'était jamais destinée au réseau B.

---

# 7. Le protocole TEST doit donc signer un domaine

Je recommande une structure conceptuelle de ce type :

```text
signature_message =
    DOMAIN_ID
    NETWORK_ID
    GENESIS_HASH
    PROTOCOL_VERSION
    WALLET_ID
    NONCE
    TRANSACTION_PAYLOAD
```

puis :

```text
HASH(signature_message)
        ↓
Ed25519 / ML-DSA
```

Donc :

```text
TEST transaction
    ↓
ARTCB-TEST
    ↓
TEST Genesis
    ↓
TEST wallet
    ↓
nonce
    ↓
payload
    ↓
signature
```

et MAINNET possède ses propres valeurs.

Ainsi :

```text
signature(TEST) != signature(MAINNET)
```

même lorsque :

```text
private_key identique
payload identique
```

---

# 8. Bonne nouvelle : le réseau possède déjà le concept nécessaire

La politique actuelle contient déjà :

```text
NETWORK_ID
PROTOCOL_VERSION
GENESIS_HASH
```

et les pairs doivent obligatoirement correspondre sur ces trois valeurs.

La fonction :

```python
accept_peer_protocol(...)
```

refuse explicitement :

```text
network_id mismatch
protocol_version mismatch
genesis_hash mismatch
```

### Donc notre TEST network pourrait avoir par exemple

```text
NETWORK_ID       = artcb-testnet-1
PROTOCOL_VERSION = 189-testnet-1
GENESIS_HASH     = genesis-artcb-testnet-1
```

Le nom exact reste à définir.

---

# 9. Cela règle aussi le problème P2P

Le P2P actuel transporte déjà :

```text
network_id
protocol_version
genesis_hash
```

dans les informations de pair/handshake.

Donc il devient possible d'avoir :

```text
MAINNET
    artcb-mainnet-1
    genesis-artcb-mainnet-1

TESTNET
    artcb-testnet-1
    genesis-artcb-testnet-1
```

et de refuser :

```text
MAINNET ↔ TESTNET
```

au niveau protocolaire.

C'est beaucoup plus solide que de simplement regarder le préfixe de l'adresse.

---

# 10. Le Genesis est également déjà conçu comme une identité de réseau

Le dépôt distingue plusieurs Genesis.

Le fichier `domains.py` confirme explicitement quatre couches :

```text
1. GLOBAL GENESIS
2. ORG GENESIS
3. GROUP GENESIS
4. USER / RESOURCE
```

et précise que les Genesis ORG/GROUP possèdent leurs propres corps et engagements publics.

Cela signifie que nous ne devons surtout pas créer :

```text
TEST = copie modifiée du Genesis MAINNET
```

Il faut créer :

```text
MAINNET GENESIS
```

et :

```text
TESTNET GENESIS
```

comme deux constitutions de réseau différentes.

---

# 11. Attention : Genesis ORG/GROUP et Genesis réseau sont différents

C'est un point important par rapport à nos audits précédents.

Le dépôt dit explicitement que :

```text
GLOBAL GENESIS
```

est partagé par les nœuds de consensus.

Alors que :

```text
ORG GENESIS
GROUP GENESIS
```

sont des constitutions de domaines avec réplication spécifique et engagement public.

Donc notre TEST doit avoir :

```text
TEST NETWORK GENESIS
        │
        ├── TEST ORG Genesis
        │
        ├── TEST GROUP Genesis
        │
        └── TEST USER/RESOURCE state
```

et non :

```text
MAINNET GENESIS
    └── toutes les données TEST
```

---

# 12. J'ai également vérifié la partie certification

Le système PBFT actuel ne considère pas simplement :

```text
certification = 100
```

comme preuve suffisante.

`pbft_certification_matrix.py` définit une matrice de certification avec des propriétés telles que :

* sécurité ;
* finalité ;
* signatures forgées ;
* Byzantine primary ;
* partitions ;
* perte de paquets ;
* duplication ;
* replay ;
* quorum ;
* view-change ;
* crash recovery ;
* convergence ;
* changement de membership ;
* agents ;
* settlement ;
* consensus de blocs.

Et surtout :

```text
CERTIFIED_100
```

exige que les lignes requises soient effectivement exécutées et qu'il n'y ait :

```text
FAIL
NOT_PROVEN
NOT_EXECUTED
SKIPPED
```

### Conséquence pour ton wallet TEST

Le wallet TEST ne doit donc **pas avoir une variable magique** :

```json
{
  "certification": 100
}
```

qui ferait croire au système qu'il est certifié.

Il faut qu'il traverse réellement la même machine de validation.

---

# 13. La bonne architecture devient donc très claire

Je propose maintenant cette architecture :

```text
                    ARTCB
                      │
              ┌───────┴────────┐
              │                │
           MAINNET            TEST
              │                │
       artcb-mainnet-1   artcb-testnet-1
              │                │
       MAINNET Genesis    TEST Genesis
              │                │
       production keys    test keys
              │                │
       real attestations  synthetic attestations
              │                │
       real identities    TEST identities
              │                │
       real economics     TEST economics
```

Mais les deux utilisent :

```text
                 SAME
          validation engine
                 │
      ┌──────────┼──────────┐
      │          │          │
    crypto     identity    PoL
      │          │          │
   device      certif      PBFT
      │          │          │
   nonce      quorum      rewards
```

---

# 14. C'est exactement ce que tu demandais

Le wallet TEST pourrait alors avoir **une seule clé privée TEST**, et changer d'état.

Par exemple :

```text
TEST-WALLET-001

        │
        ▼
P0 KEY_ONLY
        │
        ▼
P1 DEVICE_BOUND
        │
        ▼
P2 IDENTITY_BOUND
        │
        ▼
P3 IDENTITY_ATTESTED
        │
        ▼
P4 CERTIFICATION_10
        │
        ▼
P5 CERTIFICATION_25
        │
        ▼
P6 CERTIFICATION_50
        │
        ▼
P7 CERTIFICATION_75
        │
        ▼
P8 CERTIFICATION_100
        │
        ▼
P9 ACTIVE
```

Et ensuite :

```text
ACTIVE
  │
  ├── suspend
  ├── revoke
  ├── expire
  ├── recovery
  └── key rotation
```

---

# 15. Pourquoi c'est supérieur à créer 10 wallets

Aujourd'hui tu es obligé de reproduire artificiellement :

```text
wallet
→ validation
→ certification
→ autre wallet
→ autre validation
→ etc.
```

Avec le nouveau système :

```text
TEST WALLET
    │
    ├── P0
    ├── P1
    ├── P2
    ├── P3
    ├── P4
    ├── P5
    ├── ...
    └── P9
```

La **même identité de test** peut donc être utilisée pour tester toute la machine à états.

C'est beaucoup plus représentatif.

---

# 16. Très important : 10 % et 100 % ne doivent pas être des nombres arbitraires

Le système actuel nous donne déjà une indication importante avec PBFT :

```text
N
F
Q
```

et, dans le snapshot actuel de certification, le système utilise une matrice basée sur les validateurs officiels.

Donc pour notre wallet TEST, je recommande de distinguer :

### Niveau de certification

```text
CERT_10
CERT_25
CERT_50
CERT_75
CERT_100
```

de :

### Autorisation

```text
NONE
USER
ORG_MEMBER
ORG_OPERATOR
AGENT
VALIDATOR
ADMIN
...
```

**100 % certifié ne doit pas automatiquement donner les droits ADMIN.**

Sinon on mélangerait :

```text
preuve d'identité
```

avec :

```text
autorisation.
```

Ce sont deux choses différentes.

---

# 17. Comment calculer réellement les 10/100 %

Je déconseille :

```json
"certification_percent": 100
```

comme source de vérité.

Il vaut mieux avoir :

```json
{
  "certifiers": [
    "validator-A",
    "validator-B",
    "validator-C"
  ]
}
```

puis calculer :

```text
certification =
valid_unique_certifiers
/
required_certifiers
× 100
```

Par exemple :

```text
1 / 10 = 10 %
5 / 10 = 50 %
10 / 10 = 100 %
```

Cela permet de tester :

* certificat dupliqué ;
* certificat invalide ;
* certificat expiré ;
* mauvais validator ;
* validator révoqué ;
* quorum insuffisant ;
* signature falsifiée.

---

# 18. J'ai trouvé un autre point important : les rewards

Le wallet manager calcule actuellement les soldes en parcourant les `contributors` des blocs et en additionnant `reward_satoshi`.

Le `ChainManager` utilise de son côté :

```text
issued_reward_satoshi
settle_block
MachineContribution
```

et possède déjà une architecture de ledger public/private.

Cela signifie que le domaine TEST doit également isoler :

```text
TEST rewards
```

de :

```text
MAINNET rewards
```

Sinon nous aurions une faille catastrophique :

```text
TEST wallet
      ↓
TEST reward
      ↓
MAINNET balance
```

Cela doit être impossible.

---

# 19. Règle économique obligatoire

Je recommande une invariant explicite :

```text
TEST_ASSET ≠ MAINNET_ASSET
```

et :

```text
TEST → MAINNET = REJECT
MAINNET → TEST = REJECT
```

sauf mécanisme de bridge explicitement défini ultérieurement.

Pour la phase actuelle :

> **aucun bridge.**

C'est beaucoup plus simple et beaucoup plus sûr.

---

# 20. Le domaine TEST doit aussi être visible dans les blocs

Le `ChainBlock` actuel contient notamment :

```text
index
timestamp
prev_hash
graph_root
merkle_root
pol_score
hash
signature
graph_id
visibility
group_id
block_reward
contributors
hash_version
economics
```

Je recommande d'y ajouter, selon la forme exacte retenue par le protocole :

```text
network_id
genesis_id / genesis_hash
domain_id
```

ou de les intégrer obligatoirement dans le matériel cryptographiquement hashé.

Sinon le système pourrait avoir deux blocs identiques sur :

```text
payload
index
prev_hash
```

mais provenant de deux réseaux différents.

---

# 21. Les ORG/GROUP doivent également être domaine-aware

Actuellement `OrgGenesis` et `GroupGenesis` utilisent notamment :

```text
founder_address
organization_id
group_id
parent_org
parent_group_id
content_hash
```

Il faudra donc éviter qu'un :

```text
TEST ORG
```

puisse être présenté comme :

```text
MAINNET ORG
```

Je recommande que le commitment contienne explicitement le domaine :

```text
network_id
domain_id
kind
content_hash
issuer
```

Ainsi :

```text
TEST ORG X
```

et :

```text
MAINNET ORG X
```

sont deux objets distincts même si leurs noms sont identiques.

---

# 22. Il existe également une anomalie actuelle à corriger

Le mécanisme wallet/device possède actuellement :

```text
ARTCB_ALLOW_MULTI_WALLET=true
```

qui désactive complètement le contrôle.

Le commentaire du code le décrit explicitement comme un mécanisme dev/tests.

C'est utilisable pour les tests historiques, mais **ce n'est pas le mécanisme que je retiendrais pour la nouvelle architecture**.

Pourquoi ?

Parce qu'il signifie :

```text
validation OFF
```

alors que notre objectif est :

```text
validation ON
+ preuve synthétique TEST
```

C'est fondamentalement différent.

---

# 23. Le nouveau TEST doit donc supprimer cette ambiguïté

Nous devons arriver à :

```text
MAINNET
   ↓
réelle validation
   ↓
réelles preuves
```

et :

```text
TEST
   ↓
mêmes validateurs
   ↓
même moteur
   ↓
preuves synthétiques explicitement marquées TEST
```

et jamais :

```text
TEST
   ↓
validation bypass
```

---

# 24. Il faut également corriger le risque de concurrence wallet/device

Le `WalletDeviceBindingStore` fait actuellement :

```text
read JSON
    ↓
chercher fingerprint
    ↓
append
    ↓
write JSON
```

Cela ouvre potentiellement une fenêtre de course :

```text
Request A       Request B
   │               │
 read              read
   │               │
 aucun wallet      aucun wallet
   │               │
 bind              bind
   │               │
 write             write
```

Deux créations concurrentes pourraient donc potentiellement passer le contrôle.

Pour le futur mécanisme TEST/MAINNET, je recommande de traiter ce point avec un verrou transactionnel ou un stockage atomique approprié.

---

# 25. Le point que je considère maintenant comme le plus important

Après cette cartographie, je ne vois **aucune raison de créer un système parallèle complet**.

Nous avons déjà les briques :

```text
NETWORK_ID
GENESIS_HASH
PROTOCOL_VERSION
P2P compatibility
wallet derivation
Ed25519
ML-DSA
hybrid signatures
PBFT
certification matrix
public/private ledger
ORG Genesis
GROUP Genesis
rewards
PoL
```

Les références du dépôt confirment notamment la séparation réseau/protocole/Genesis, les Genesis de domaine et la matrice PBFT.

Le travail consiste donc à **ajouter un premier-class TEST domain à l'architecture existante**, pas à construire une deuxième blockchain artificielle.

---

# 26. Architecture cible que je retiens

```text
                     ARTCB PROTOCOL
                           │
             ┌─────────────┴─────────────┐
             │                           │
       PRODUCTION DOMAIN             TEST DOMAIN
             │                           │
       artcb-mainnet-1             artcb-testnet-1
             │                           │
       Mainnet Genesis               Test Genesis
             │                           │
       production wallet             test wallet
             │                           │
       real attestations          synthetic attestations
             │                           │
       real device proof           synthetic device proof
             │                           │
       real identity               TEST identity
             │                           │
       real certification          simulated certification
             │                           │
       real economics              isolated economics
             │                           │
             └─────────────┬─────────────┘
                           │
                    SAME VALIDATORS
                    SAME VALIDATION
                    SAME PROTOCOL
                    SAME STATE MACHINE
```

Avec une règle absolue :

```text
MAINNET state
     ≠
TEST state
```

et :

```text
MAINNET signature
     ≠
TEST signature
```

et :

```text
MAINNET Genesis
     ≠
TEST Genesis
```

---

# 27. Les phases que je propose de graver dans le modèle

Je retiens finalement cette machine :

| Phase               | Ce qu'elle signifie              |
| ------------------- | -------------------------------- |
| `KEY_ONLY`          | clé cryptographique valide       |
| `DEVICE_BOUND`      | appareil TEST correctement lié   |
| `IDENTITY_BOUND`    | identité TEST associée           |
| `IDENTITY_ATTESTED` | attestation valide               |
| `CERT_10`           | seuil 10 % réellement obtenu     |
| `CERT_25`           | seuil 25 %                       |
| `CERT_50`           | seuil 50 %                       |
| `CERT_75`           | seuil 75 %                       |
| `CERT_100`          | totalité du seuil requis         |
| `ACTIVE`            | identité autorisée à fonctionner |
| `SUSPENDED`         | temporairement suspendue         |
| `EXPIRED`           | preuve arrivée à expiration      |
| `REVOKED`           | identité révoquée                |
| `RECOVERY`          | procédure de récupération        |
| `ROTATION_PENDING`  | rotation de clé en cours         |
| `ROTATED`           | nouvelle clé active              |

Et chaque transition doit être validée.

Par exemple :

```text
KEY_ONLY → CERT_100
```

**doit être refusé.**

Alors que :

```text
KEY_ONLY
 → DEVICE_BOUND
 → IDENTITY_BOUND
 → IDENTITY_ATTESTED
 → CERT_10
 → CERT_25
 → CERT_50
 → CERT_75
 → CERT_100
 → ACTIVE
```

est valide.

---

# 28. Tests adversariaux indispensables

Le futur test wallet devra également pouvoir provoquer volontairement :

```text
BAD_SIGNATURE
WRONG_PUBLIC_KEY
WRONG_PRIVATE_KEY
WRONG_DEVICE
EXPIRED_ATTESTATION
REVOKED_IDENTITY
REPLAY
BAD_NONCE
DUPLICATE_CERTIFIER
UNKNOWN_VALIDATOR
REVOKED_VALIDATOR
INSUFFICIENT_QUORUM
WRONG_NETWORK_ID
WRONG_GENESIS
WRONG_PROTOCOL_VERSION
TEST_TO_MAINNET
MAINNET_TO_TEST
UNAUTHORIZED_AGENT
```

L'intérêt est majeur :

**on ne vérifie pas seulement que le wallet fonctionne.**

On vérifie qu'il est rejeté exactement comme un vrai wallet lorsqu'une condition de sécurité est violée.

---

# 29. État de l'audit à ce stade

### Confirmé dans le code

| Élément                            | État                                    |
| ---------------------------------- | --------------------------------------- |
| Adresse Bech32                     | **CONFIRMÉ**                            |
| Préfixe d'adresse configurable     | **CONFIRMÉ**                            |
| Ed25519                            | **CONFIRMÉ**                            |
| ML-DSA / hybride                   | **CONFIRMÉ**                            |
| Network ID                         | **CONFIRMÉ**                            |
| Protocol version                   | **CONFIRMÉ**                            |
| Genesis identifier                 | **CONFIRMÉ**                            |
| Compatibilité P2P                  | **CONFIRMÉE**                           |
| Genesis ORG/GROUP                  | **CONFIRMÉ**                            |
| Public/private ledger              | **CONFIRMÉ**                            |
| PBFT certification matrix          | **CONFIRMÉE**                           |
| Rewards                            | **CONFIRMÉ**                            |
| Device binding                     | **CONFIRMÉ**                            |
| Test wallet réellement isolé       | **NON ENCORE IMPLÉMENTÉ**               |
| Domain-bound wallet hash           | **NON ENCORE IMPLÉMENTÉ**               |
| Domain-bound transaction signature | **NON ENCORE CONFIRMÉ / À IMPLÉMENTER** |
| TEST economic ledger isolé         | **À IMPLÉMENTER**                       |
| TEST Genesis dédié                 | **À IMPLÉMENTER**                       |
| TEST identity state machine        | **À IMPLÉMENTER**                       |

---

# 30. Conclusion de cette étape

Le dépôt actuel **supporte beaucoup mieux cette architecture que ce que la première recherche laissait apparaître**.

Le point déterminant est que `NETWORK_ID + PROTOCOL_VERSION + GENESIS_HASH` sont déjà des paramètres de compatibilité protocolaire obligatoires.

Donc je recommande maintenant de ne **pas** appeler cela simplement « wallet de développement ».

Le bon objet architectural est :

> **ARTCB TEST DOMAIN / TEST WALLET**

avec :

```text
adresse distincte
+
clé distincte
+
Genesis distinct
+
network_id distinct
+
signature domain-separated
+
ledger économique distinct
+
identité TEST explicite
+
preuves synthétiques
+
même moteur de validation
+
mêmes règles de rejet
```

Et surtout : **aucune validation de production ne doit être supprimée pour obtenir cette facilité de test.**

### Prochaine étape technique que je recommande

La cartographie suivante doit maintenant descendre d'un niveau supplémentaire et suivre **le trajet complet d'une transaction réelle**, depuis :

```text
wallet.sign()
```

jusqu'à :

```text
transaction
 → hash
 → signature
 → nonce
 → API
 → validation
 → PoL
 → certification
 → settlement
 → block
 → PBFT
 → reward
 → balance
```

C'est cette chaîne précise qui permettra de déterminer **les emplacements exacts où `TEST_DOMAIN` doit être injecté**, et surtout de vérifier qu'il n'existe aucun chemin secondaire permettant à une transaction `artcbdev...` de parvenir au ledger `artcb-mainnet-1`.
