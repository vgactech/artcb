Oui. **Je corrige le rapport précédent sur ce point précis : ton interdiction est absolue.**

J'avais conservé une formulation qui laissait entendre que **le PIN local d'un authenticator pouvait être accepté comme élément du modèle ARTCB**. Ce n'est pas conforme à ta décision.

## Nouvelle règle ARTCB — verrouillée

Il faut distinguer :

* **Face ID / Touch ID / biométrie native** : mécanisme local de l'appareil ;
* **PIN/code de l'authenticator** : mécanisme local de déverrouillage de l'authenticator ;
* **WebAuthn** : mécanisme cryptographique qui produit l'assertion/signature ;
* **ARTCB** : ne doit recevoir **ni PIN, ni mot de passe, ni code local, ni secret local**.

Le rapport précédent disait que le PIN local « reste possible ». **Je retire cette formulation.**

### Le modèle que tu imposes est :

```text
                 UTILISATEUR
                     │
                     ▼
              APPAREIL CLIENT
                     │
          ┌──────────┴──────────┐
          │                     │
      Touch ID              Face ID
      ou autre              ou autre
      biométrie             biométrie
      native                native
          │                     │
          └──────────┬──────────┘
                     │
                     ▼
              AUTHENTICATOR
                     │
                     ▼
            CREDENTIAL WEBAUTHN
                     │
                     ▼
              SIGNATURE CRYPTO
                     │
                     ▼
                   ARTCB
```

**Le PIN/code local n'est pas une branche alternative du protocole ARTCB.**

Même s'il est utilisé intérieurement par un authenticator pour permettre l'utilisation de sa credential, **ARTCB ne doit pas considérer son existence, sa validité ou sa valeur comme une preuve reçue du client.**

C'est une distinction importante.

---

# 1. Ce qu'ARTCB doit accepter

Pour la voie biométrique que tu conserves :

```text
Biométrie native de l'appareil
        ↓
Authenticator natif
        ↓
Credential WebAuthn
        ↓
Assertion cryptographique
        ↓
ARTCB
```

ARTCB vérifie alors les propriétés cryptographiques et protocolaires attendues.

Les anciens audits avaient déjà décrit ce flux comme :

> appareil → Face ID/empreinte → authenticator → WebAuthn → signature cryptographique → serveur ARTCB. 

Mais **il faut maintenant retirer explicitement le PIN de la spécification ARTCB**, même lorsqu'il existe éventuellement à l'intérieur du fonctionnement de l'authenticator.

---

# 2. Ce qu'ARTCB doit refuser

Je veux que la spécification soit beaucoup plus stricte que le précédent rapport.

| Entrée présentée à ARTCB                                                 | Décision     |
| ------------------------------------------------------------------------ | ------------ |
| PIN envoyé à l'API                                                       | ❌ REJET      |
| PIN envoyé dans JSON                                                     | ❌ REJET      |
| PIN dans header HTTP                                                     | ❌ REJET      |
| mot de passe comme preuve biométrique                                    | ❌ REJET      |
| code local présenté comme preuve d'identité                              | ❌ REJET      |
| secret applicatif                                                        | ❌ REJET      |
| `biometric=true` sans preuve cryptographique                             | ❌ REJET      |
| `face=true`                                                              | ❌ REJET      |
| `human_verified=true` auto-déclaré                                       | ❌ REJET      |
| résultat `face_camera` ARTCB                                             | ❌ REJET      |
| reconnaissance faciale ARTCB                                             | ❌ REJET      |
| liveness applicatif ARTCB                                                | ❌ REJET      |
| assertion WebAuthn cryptographiquement valide + exigences UV satisfaites | ✅ ACCEPTABLE |

La règle fondamentale devient donc :

> **Une valeur déclarée par le client ne peut jamais devenir une preuve simplement parce qu'elle porte le nom `biometric`, `human`, `verified`, `face`, `uv`, etc.**

---

# 3. Et surtout : ne pas confondre « PIN utilisé par l'appareil » et « PIN accepté par ARTCB »

C'est là que se trouvait mon erreur.

Supposons qu'un téléphone fasse intérieurement :

```text
Utilisateur
   ↓
PIN local
   ↓
Authenticator
   ↓
clé privée
   ↓
signature WebAuthn
```

ARTCB ne voit pas nécessairement le PIN.

Mais **ARTCB ne doit pas non plus créer une règle disant :**

```text
"si l'authenticator a utilisé un PIN local,
alors j'accepte le PIN comme méthode d'identité."
```

Non.

Pour ARTCB, la seule chose pertinente au niveau serveur est la **preuve WebAuthn vérifiable** et les propriétés que le protocole est effectivement capable d'établir.

Donc :

```text
PIN local
   │
   └── mécanisme interne éventuel de l'authenticator
             │
             ▼
       hors protocole ARTCB
```

et :

```text
WebAuthn assertion
       │
       ▼
    ARTCB
```

C'est la frontière à conserver.

---

# 4. La caméra ARTCB doit également disparaître du modèle actif

Sur ce point, je conserve ta correction précédente.

L'ancien audit identifiait encore une voie caméra où l'on pouvait arriver à quelque chose ressemblant à :

```text
caméra
 ↓
visage détecté
 ↓
liveness_ok
 ↓
wallet
```

Le rapport avait justement signalé que cette séquence ne suffisait pas à démontrer une identité humaine unique. 

Mais avec ta décision actuelle, on va plus loin :

```text
face_camera
     ↓
     ❌
```

Pas :

```text
face_camera
     ↓
niveau de sécurité inférieur
```

et pas :

```text
face_camera
     ↓
fallback
```

**La voie doit être inactive.**

Même chose pour :

* reconnaissance faciale ARTCB ;
* analyse faciale ARTCB ;
* liveness facial ARTCB ;
* caméra utilisée pour créer un wallet ;
* caméra utilisée pour authentifier un wallet.

---

# 5. Il reste néanmoins une distinction essentielle concernant WebAuthn

Je ne veux pas faire une deuxième erreur en allant trop loin dans l'autre sens.

**WebAuthn ne signifie pas automatiquement « preuve d'un humain unique ».**

Les anciens audits avaient déjà correctement séparé ces propriétés : une authentification WebAuthn peut établir une preuve cryptographique liée à une credential, mais elle ne démontre pas automatiquement qu'une personne est une personne humaine unique dans l'ensemble du réseau. 

Donc ARTCB doit avoir quelque chose de conceptuellement similaire à :

```text
WEBAUTHN_AUTHENTICATED
        │
        ▼
credential cryptographique valide
        │
        ▼
appareil/authenticator vérifié
        │
        ▼
UV conforme aux exigences
```

Mais **pas** :

```text
WebAuthn
   ↓
UNIQUE_HUMAN
```

Cette dernière implication doit être démontrée par un mécanisme supplémentaire si le protocole veut réellement utiliser `UNIQUE_HUMAN`.

---

# 6. Ce que je considère maintenant comme le modèle de référence

### Couche appareil

```text
Appareil client
 ├── Touch ID
 ├── Face ID
 └── autre biométrie native compatible
```

### Couche authenticator

```text
Authenticator natif
       ↓
Credential WebAuthn
```

Le mécanisme local de déverrouillage de l'authenticator — **qu'il soit biométrique, PIN ou autre — reste local à cet authenticator et ne devient jamais une entrée d'identité ARTCB.**

### Couche réseau

```text
WebAuthn assertion
       ↓
ARTCB
       ↓
vérification cryptographique
       ↓
autorisation
       ↓
wallet
```

### Couche interdite

```text
PIN → ARTCB                       ❌
password → ARTCB                 ❌
secret → ARTCB                   ❌
face_camera → wallet             ❌
face recognition ARTCB → wallet  ❌
client says human_verified=true  ❌
client says biometric=true       ❌
```

---

# 7. Conséquence pour les anciens wallets

C'est également important.

Les anciens audits avaient conclu que les wallets déjà créés ne devaient pas être automatiquement qualifiés d'« identités humaines uniques » simplement parce qu'ils avaient été créés pendant les tests. 

Avec ta nouvelle règle, il faut maintenant auditer chaque wallet selon sa **méthode réelle de création** :

```text
WALLET
  │
  ├── méthode = WebAuthn natif + preuve conforme
  │       → examiner comme wallet WebAuthn
  │
  ├── méthode = PIN envoyé au serveur
  │       → ❌ méthode interdite
  │
  ├── méthode = face_camera ARTCB
  │       → ❌ voie interdite
  │
  └── méthode inconnue
          → ❓ à auditer
```

Et surtout, **le fait que tu sois le créateur du projet ne doit pas produire une exception**. L'ancien audit l'avait déjà établi : ton rôle de créateur ne remplace pas les garanties que le protocole doit fournir. 

---

# 8. Correction définitive du rapport précédent

Je remplace donc mentalement cette ancienne phrase :

> « Le PIN local de l'authenticator WebAuthn reste possible »

par :

> **« ARTCB n'accepte aucun PIN, code local, mot de passe ou secret comme preuve d'identité ou de biométrie. Le fonctionnement interne éventuel d'un authenticator — y compris un mécanisme local de déverrouillage — reste hors du protocole ARTCB. La voie d'identité retenue côté ARTCB repose sur une credential/assertion WebAuthn vérifiée cryptographiquement, avec les propriétés d'authenticator et de vérification utilisateur effectivement contrôlables par le serveur. »**

C'est cette formulation qui doit désormais servir de **référence pour les prochains audits biométrie / wallet / WebAuthn**.

### Et il y a une conséquence importante pour l'audit du dépôt

Le prochain contrôle ne doit donc **pas seulement chercher `PIN` dans le code**. Il doit vérifier toute la chaîne :

```text
Frontend
   ↓
API
   ↓
schémas JSON
   ↓
routes d'inscription
   ↓
routes de login
   ↓
WebAuthn
   ↓
wallet creation
   ↓
face_camera
   ↓
tests
   ↓
documentation
```

avec deux objectifs simultanés :

1. **prouver qu'aucun PIN/code local n'est accepté comme preuve par ARTCB** ;
2. **prouver qu'aucune ancienne voie caméra/face applicative ne peut contourner WebAuthn**.

C'est ce contrôle de divergence **code réel ↔ API ↔ frontend ↔ tests ↔ comportement** qu'il faut faire maintenant, plutôt que de considérer l'Issue #89 comme suffisante.
