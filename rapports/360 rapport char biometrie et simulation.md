Oui. J’ai repris la recherche **en remontant volontairement avant les rapports 208–215**, parce que ton reproche est justifié : les rapports récents ont mis l’accent sur l’état d’implémentation et ont fait perdre de vue une décision antérieure importante.

Je n’ai **rien modifié dans GitHub**.

## 1. Correction importante de mon audit précédent : les 100 validateurs ont bien été étudiés et intégrés comme décision

J’ai retrouvé la trace explicite dans **le rapport 162 et les artefacts de simulation associés**.

Le rapport 162 définit bien un mécanisme **Finder Q=100** :

> `Q=100`
> « Normal humans: up to 100 independent admissible validations. »
> « When validator count > 100, creator-direct validations become revalidation-eligible. »

Et surtout, la simulation du rapport 162 contient réellement la logique :

> `Creator validates first 99, then revalidation when validators>100`

Elle simule même le passage à plus de 100 validateurs :

* `Q = 100`
* créateur bootstrap direct ;
* revalidation lorsque le nombre de validateurs dépasse 100 ;
* à 120 inscriptions, le modèle arrive à **101 validateurs** ;
* `genesis_validated_count = 101`.

Et le rapport 162 présente cette architecture comme une décision consolidée, au milieu des autres règles économiques et d'identité.

### Donc oui : tu avais raison sur ce point.

J'avais précédemment fait une distinction correcte entre :

**« 100 validateurs existent dans une simulation/décision »**

et

**« le mécanisme complet est actuellement opérationnel sur le parcours utilisateur live »**.

Mais j'ai été trop loin en donnant l'impression que **le concept des 100 validateurs n'avait pas été retenu**.

Ce n'est pas exact.

---

# 2. Et encore plus important : le code actuel contient maintenant `identity.py` issu du rapport 162

J'ai vérifié directement `main`.

Le fichier existe :

`src/artcb/economics/identity.py`

et son en-tête dit explicitement :

> `Identity / Finder Q=100 — rapport 162.`

Il définit :

```text
Q_FINDER = 100
```

ainsi que les états :

```text
CANDIDATE
GENESIS_VALIDATED
VERIFIED
REVALIDATION_REQUIRED
REVALIDATED
SUSPENDED
```

Le créateur Genesis peut être bootstrapé, puis les validations Finder sont comptabilisées.

Donc il y a bien eu **passage de la décision/simulation vers du code**.

Mais — et c'est crucial — cela **ne signifie pas que le protocole complet est déjà fonctionnel comme tu le décris**.

---

# 3. Le problème que je viens de retrouver dans cette implémentation est précisément celui que tu veux éviter

Regarde la fonction actuelle :

```text
add_finder_validation(human_id)
```

Elle reçoit uniquement le `human_id`.

Elle ne reçoit pas :

```text
validator_id
```

ni :

```text
validator_wallet
validator_human_id
validator_credential
validator_identity
```

Donc le code actuel sait essentiellement dire :

> « une validation supplémentaire a été ajoutée à cette personne »

mais il ne démontre pas encore :

> « cette validation a été réalisée par **un humain différent et admissible**, et cet humain n'a jamais déjà validé cette même identité ».

C'est une différence fondamentale.

### Exemple

Supposons :

```text
Alice = candidate
```

Le protocole doit obtenir :

```text
Validator 001 → Alice
Validator 002 → Alice
Validator 003 → Alice
...
Validator 100 → Alice
```

avec :

```text
001 ≠ 002 ≠ 003 ≠ ... ≠ 100
```

et chaque validator doit lui-même être un humain certifié.

Or l'implémentation actuelle possède un compteur :

```text
validation_count += 1
```

mais pas, dans cette fonction, un registre cryptographiquement vérifiable du type :

```text
Alice
 ├── Validator H001
 ├── Validator H017
 ├── Validator H084
 ├── Validator H193
 └── ...
```

Donc **Q=100 est codé comme mécanisme de comptage**, mais la propriété fondamentale **100 humains indépendants** n'est pas encore démontrée par ce code seul.

C'est exactement le genre de différence que nous devons continuer à surveiller.

---

# 4. Et cela change fortement ton nouveau plan biométrique

Tu proposes maintenant une architecture beaucoup plus claire :

```text
INSCRIPTION
     │
     ▼
CRÉATION WALLET
     │
     ▼
BIOMÉTRIE DIGITALE
     │
     ▼
IDENTITÉ HUMAINE UNIQUE
     │
     ▼
AUTORISATION DE LA CERTIFICATION
     │
     ▼
SÉLECTION DE 100 VALIDATEURS
     │
     ▼
100 VALIDATIONS INDÉPENDANTES
     │
     ▼
HUMAIN CERTIFIÉ
```

Et tu veux supprimer :

```text
FACE
CAMÉRA
LIVENESS FACIAL
FACE LOGIN
```

du parcours.

**Je comprends la logique.**

Mais il faut faire une distinction cryptographique extrêmement importante.

---

# 5. « Empreinte digitale unique » ≠ « clé cryptographique unique »

C'est probablement le point technique le plus important de toute ta demande.

Il existe deux choses différentes.

### A. Empreinte cryptographique

Par exemple :

```text
SHA-256(public_key)
```

C'est une empreinte mathématique d'une donnée.

Elle est parfaitement déterministe.

### B. Empreinte digitale biométrique

C'est le motif physique du doigt.

Un téléphone peut utiliser ce motif pour décider :

```text
oui → c'est probablement l'utilisateur autorisé
non → accès refusé
```

Mais normalement, le système biométrique **ne donne pas au serveur le scan brut du doigt**.

Il le conserve dans le composant sécurisé du téléphone.

---

# 6. C'est précisément pourquoi le simple stockage d'un hash du doigt ne résout pas ton problème

Le rapport 162 avait justement retenu :

```text
biometric_raw_never_on_chain = true
```

La simulation le documente explicitement.

Et la matrice actuelle du projet conserve cette règle :

> `HumanIdentity via verifiable credential; no raw biometrics on-chain`

avec le principe :

> `wallet creation ≠ unique human proof`.

Donc **je ne recommande absolument pas de graver l'image ou le template biométrique brut dans un bloc**.

Cela créerait notamment :

* un problème majeur de confidentialité ;
* un identifiant biométrique permanent ;
* une impossibilité pratique de « changer son doigt » si la donnée fuit ;
* un problème de corrélation entre wallets ;
* des problèmes de conformité et de gouvernance ;
* et surtout cela ne garantit pas automatiquement une comparaison inter-appareils.

---

# 7. Le vrai problème : un téléphone A et un téléphone B ne partagent pas nécessairement la même représentation biométrique

Exemple :

```text
Téléphone A
     │
     └── empreinte digitale de Jean
             ↓
       Secure Enclave / TEE
```

Puis :

```text
Téléphone B
     │
     └── même doigt de Jean
             ↓
       autre Secure Enclave / TEE
```

Le serveur ne reçoit normalement pas :

```text
fingerprint_raw = ...
```

et ne peut donc pas simplement faire :

```text
hash(finger_A) == hash(finger_B)
```

Ce mécanisme n'existe pas automatiquement.

---

# 8. Ce que WebAuthn fait réellement aujourd'hui

Le dépôt possède actuellement une vraie couche WebAuthn et une page `RegisterBiometric`. Elle expose notamment :

* empreinte ;
* Face ID / authentificateur de plateforme ;
* caméra ;
* login biométrique.

Le rapport 208 documente aussi :

```text
webauthn_routes.py
auth_routes.py
RegisterBiometric.tsx
FaceCapture.tsx
```

avec caméra + liveness locale.

Mais **WebAuthn ne signifie pas que le serveur connaît l'empreinte digitale**.

Le modèle est plutôt :

```text
Doigt
  ↓
OS / authentificateur sécurisé
  ↓
déverrouille l'utilisation d'une clé WebAuthn
  ↓
signature cryptographique
  ↓
serveur
```

Le serveur vérifie donc une **signature**, pas directement le doigt.

---

# 9. C'est justement là que ton nouveau modèle peut devenir beaucoup plus propre

Je vois une architecture cible en trois niveaux.

## Niveau 1 — Biométrie digitale locale

Le doigt déverrouille l'authentificateur.

Le serveur reçoit :

```text
credential_id
public_key
signature
challenge
```

et non le doigt brut.

---

## Niveau 2 — Identité humaine unique ARTCB

Il faut ensuite créer un objet protocolaire du genre :

```text
HumanID
     │
     ├── WalletID
     ├── WebAuthn credential(s)
     ├── validation status
     └── Finder certification status
```

Et surtout :

```text
HumanID ≠ DeviceID
```

car une personne peut avoir :

```text
PC
smartphone
tablette
autre navigateur
```

tout en restant :

```text
1 humain
```

C'est cohérent avec le travail antérieur sur le binding humain/machine.

---

# 10. Mais ton exigence supplémentaire est plus forte

Tu demandes :

> si quelqu'un essaie d'utiliser **la même biométrie digitale** pour créer/valider un autre wallet, il doit être bloqué, même depuis un autre téléphone ou PC.

Cela signifie que tu veux une propriété :

```text
BiometricIdentity
        ↓
      UNIQUE
        ↓
    HumanID
        ↓
   1 wallet principal
```

et non :

```text
DeviceID → Wallet
```

C'est une amélioration conceptuelle importante.

Le système actuel possède justement une `DeviceRegistry` et une `WalletIdRegistry`, mais cela reste orienté vers :

```text
DeviceID
HumanID
WalletID
```

et non vers une **preuve biométrique inter-appareils indépendante**. Le code actuel précise d'ailleurs que le fingerprint du device est un hash et non un numéro matériel brut.

---

# 11. Donc le Device Binding actuel ne suffit PAS

Actuellement :

```text
Machine A
   ↓
DeviceID A
   ↓
Wallet A
```

puis :

```text
Machine B
   ↓
DeviceID B
   ↓
Wallet B
```

Le système peut bloquer certaines réutilisations d'appareil.

Mais cela ne prouve pas :

```text
Humain A
   ↓
doigt A
   ↓
Wallet A

Humain A
   ↓
même doigt A
   ↓
Wallet B
```

Le deuxième doit être refusé selon ta nouvelle règle.

**C'est précisément le trou que nous devons fermer.**

---

# 12. Le bon modèle cible

Je le représenterais ainsi :

```text
                   ┌──────────────────────┐
                   │  BIOMÉTRIE DIGITALE  │
                   └──────────┬───────────┘
                              │
                              ▼
                   Authenticator sécurisé
                              │
                              ▼
                    Preuve cryptographique
                              │
                              ▼
                       ┌─────────────┐
                       │   HumanID   │
                       └──────┬──────┘
                              │
                 ┌────────────┼────────────┐
                 ▼            ▼            ▼
             WalletID      Device A      Device B
                 │
                 │
                 ▼
          Finder Q = 100
                 │
                 ▼
       100 validateurs humains
                 │
                 ▼
       HUMAN VERIFIED / CERTIFIED
```

Le point important est :

### Le téléphone n'est plus l'identité.

### Le navigateur n'est plus l'identité.

### La machine n'est plus l'identité.

Ils deviennent seulement des moyens d'accès.

---

# 13. Et je confirme que le principe Q=100 existait déjà dans les anciennes simulations

La simulation 162 va même jusqu'à tester :

```text
bindings.setdefault(human, []).append(machine)
```

puis :

```text
Creator validates first 99
```

et la revalidation lorsque le réseau dépasse 100 validateurs.

L'artefact `08_identity_machines.json` contient :

```text
Q: 100
creator_direct_bootstrap: true
revalidation_when_validators_gt_100: true
validators_after_120_inscriptions_model: 101
genesis_validated_count: 101
```

Donc cette partie ne doit **pas être supprimée de la conception** sous prétexte que les derniers audits n'en parlaient plus.

---

# 14. Mais attention à un autre détail : « 100 validateurs aléatoires disponibles en ligne »

Cela doit être précisé.

Le système cible ne doit pas faire :

```text
choisir 100 wallets quelconques
```

Il doit faire :

```text
POOL DES VALIDATEURS ÉLIGIBLES
             │
             ▼
filtrage
             │
             ├── HumanID valide
             ├── biométrie authentifiée
             ├── wallet valide
             ├── non suspendu
             ├── pas conflit d'intérêt
             ├── n'a pas déjà validé cette personne
             └── disponible
             │
             ▼
sélection pseudo-aléatoire vérifiable
             │
             ▼
100 validateurs
```

### « Aléatoire » doit être vérifiable.

Sinon quelqu'un pourrait contrôler la sélection.

Idéalement :

```text
selection_seed =
    hash(
       block_hash
       || candidate_id
       || protocol_epoch
    )
```

puis une sélection déterministe dans l'ensemble des validateurs admissibles.

---

# 15. Et chaque validation doit être réellement individuelle

Il faut pouvoir reconstruire :

```text
Candidate H999

Validator H001 → APPROVE
Validator H017 → APPROVE
Validator H024 → APPROVE
Validator H039 → REJECT
Validator H052 → APPROVE
...
Validator H876 → APPROVE
```

avec :

```text
100 ValidatorID distincts
```

et pas :

```text
validation_count = 100
```

C'est une différence capitale.

---

# 16. Le système actuel `identity.py` est donc à classer ainsi

| Élément                                          | État constaté                       |
| ------------------------------------------------ | ----------------------------------- |
| Concept Finder Q=100                             | **DÉCIDÉ**                          |
| Simulation Q=100                                 | **FAITE**                           |
| Simulation >100 validateurs                      | **FAITE**                           |
| Code `Q_FINDER=100`                              | **PRÉSENT**                         |
| HumanRegistry                                    | **PRÉSENT**                         |
| Creator Genesis bootstrap                        | **PRÉSENT**                         |
| Validation Finder comptée                        | **PRÉSENT**                         |
| Revalidation >100                                | **PRÉSENTE dans le code**           |
| Identité biométrique digitale globale            | **NON DÉMONTRÉE**                   |
| Même doigt → second wallet bloqué cross-device   | **NON DÉMONTRÉ**                    |
| 100 validateurs réellement distincts             | **NON DÉMONTRÉ PAR LE CODE ACTUEL** |
| Sélection aléatoire vérifiable de 100            | **NON DÉMONTRÉE**                   |
| UI complète de certification Q=100               | **NON DÉMONTRÉE**                   |
| Certification live d'un humain par 100 personnes | **NON DÉMONTRÉE**                   |

---

# 17. Concernant la reconnaissance faciale : tu veux maintenant la désactiver

**Je n'ai rien modifié.**

Et l'état actuel confirme qu'elle est encore présente.

`RegisterBiometric.tsx` contient encore :

```text
fingerprint | face | both
```

et `mode = register | login`.

Le `App.tsx` référence encore `RegisterBiometric`.

Et les tests frontend vérifient encore explicitement le vocabulaire « présence faciale » plutôt que « reconnaissance ».

Donc :

**la désactivation n'est pas encore faite dans le dépôt actuel.**

---

# 18. Je ne supprimerais surtout pas seulement le bouton UI

Si nous décidons officiellement de retirer le facial, il faudra auditer toute la chaîne :

```text
UI
 ↓
routes frontend
 ↓
API
 ↓
session/authentication
 ↓
tests
 ↓
traductions
 ↓
configuration
 ↓
documentation
 ↓
simulations
 ↓
certification/assurance
```

Sinon on aurait :

```text
UI : facial caché
API : facial encore actif
```

ou :

```text
UI : facial supprimé
tests : facial encore attendu
```

ou pire :

```text
UI : fingerprint only
backend : caméra encore capable de produire une assurance
```

Le rapport 208 montre justement que les routes `auth/webauthn/*` et `auth/face/*` sont liées à la même couche d'authentification.

Donc il faut traiter cela comme **une suppression de capacité**, pas simplement comme une modification visuelle.

---

# 19. Et je conserverais une règle importante du rapport 162

Le rapport 162 avait déjà posé :

```text
biometric_raw_never_on_chain = true
```

Je conserverais cette règle.

La solution que je recommande n'est donc **pas** :

```text
empreinte digitale brute
       ↓
bloc blockchain
```

mais plutôt :

```text
empreinte
   ↓
authentificateur sécurisé
   ↓
preuve cryptographique
   ↓
HumanID
   ↓
unicité / anti-réutilisation
   ↓
100 validateurs
   ↓
certification
```

---

# 20. État global après cette recherche historique

La conclusion est maintenant beaucoup plus précise.

### Ce qui avait été décidé

**Oui :**

* HumanID ;
* Human Binding ;
* Finder Q=100 ;
* validations humaines indépendantes ;
* comportement spécial du créateur Genesis ;
* revalidation lorsque le réseau dépasse le seuil ;
* liaison de l'identité avec les éléments économiques ;
* biométrie sans biométrie brute inscrite sur chaîne.

Ces éléments sont bien retrouvés dans les travaux antérieurs, notamment autour du rapport 162.

### Ce qui a commencé à être codé

**Oui :**

* `HumanRegistry`;
* `HumanID`;
* Q=100 ;
* états de certification ;
* creator Genesis ;
* compteur Finder ;
* revalidation ;
* `DeviceRegistry`;
* `WalletIdRegistry`.

### Ce qui n'est pas encore démontré comme protocole complet

**Non démontré :**

* unicité biométrique digitale inter-device ;
* blocage du même doigt sur un deuxième wallet ;
* preuve que 100 validations proviennent de 100 humains différents ;
* sélection réellement aléatoire et vérifiable des 100 ;
* workflow live complet ;
* certification finale déclenchée automatiquement après preuve biométrique ;
* UI complète de cette certification.

---

## Et surtout : je retiens maintenant correctement la chaîne historique

```text
RAPPORTS ANCIENS
      ↓
HumanID / Human Binding
      ↓
RAPPORT 162
      ↓
Finder Q=100
      ↓
SIMULATION Q=100
      ↓
CODE identity.py
      ↓
AUDITS 208+
      ↓
WebAuthn / biométrie
      ↓
constat : biométrie ≠ encore preuve d'humain unique
      ↓
NOUVELLE DIRECTION
      ↓
BIOMÉTRIE DIGITALE UNIQUEMENT
      ↓
HumanID unique
      ↓
100 validateurs humains indépendants
      ↓
CERTIFICATION
```

**C'est cette chaîne complète qu'il faut désormais suivre.** Je ne dois plus prendre le dernier rapport isolément comme s'il remplaçait les décisions précédentes.

Et je n'ai effectué **aucune modification** dans le dépôt.
