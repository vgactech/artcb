Oui. J’ai fait le contrôle en croisant **le rapport 220 avec le code réel de `main`, le test E2E, le script de mesure live et l’historique Git**, plutôt que de prendre le rapport comme preuve suffisante.

GitHub

## 1. État réellement vérifié

Le `main` actuel est maintenant `05c55e2d9e1d61d90cf3b60283007a69cd246e86`, signé, et son parent direct est précisément `9a536689f38a25da147df7f1ea4f28ff1ab5d375`, qui est le SHA annoncé comme présent sur les quatre nœuds lors de la mesure live. Le dernier commit n'ajoute que des modifications au rapport 220, à la liste de tests et au script live : il ne modifie donc pas la logique métier qui a été mesurée.

C'est important :

> **le rapport 220 n'est pas en train de décrire une version de code ultérieure différente de celle testée sur OVH1.**

Le commit post-live est documentaire/outillage. La comparaison Git le confirme.

---

# 2. Ce qui est réellement implémenté

### A. Le Genesis privé n'est toujours pas envoyé sur la blockchain publique

Le code `domains.py` distingue explicitement :

```text
GLOBAL GENESIS
ORG GENESIS
GROUP GENESIS
USER / RESOURCE
```

et définit le corps ORG/GROUP comme une donnée de domaine, tandis que le réseau global ne reçoit qu'un **engagement cryptographique** : `kind + domain_id + content_hash`.

**C'est-à-dire :**

Imagine :

```text
Genesis ORG
│
├── nom
├── constitution
├── règles
├── autorisations
├── éventuellement informations internes
└── membres / données privées
```

Le réseau public ne reçoit pas cette boîte.

Il reçoit plutôt :

```text
ORG_ID = ABC123
HASH   = 7f8a...
PARENT = ...
ISSUER = ...
```

Donc :

> **le hash prouve qu'un contenu précis existait à un moment donné, mais ne révèle normalement pas le contenu lui-même.**

C'est le mécanisme classique de **commitment cryptographique**.

---

# 3. Et le bloc public est réellement construit comme ça

Le code `anchor.py` force :

* `visibility="public"`
* `block_reward=0`
* `pol_score=0`
* seulement les symboles publics
* aucun Genesis
* aucun membre
* aucun document.

Donc le système ne fait pas :

```text
ORG créée
   ↓
Genesis
   ↓
bloc public contenant Genesis
```

Il fait :

```text
ORG créée
       │
       ├── Genesis privé
       │       └── domaine local
       │
       └── HASH Genesis
                │
                ▼
       bloc public reward = 0
```

### Pourquoi `reward=0` est important ?

Parce que ce bloc n'est **pas un bloc de minage**.

C'est-à-dire qu'ARTCB ne doit pas pouvoir être attaqué économiquement comme ceci :

> « Je crée 1 million d'organisations uniquement pour générer 1 million de récompenses. »

Le bloc d'ancrage ne crée pas de monnaie.

C'est une **preuve publique**, pas une émission monétaire.

---

# 4. Le transfert d'autorité est maintenant réellement séparé du Genesis

C'est probablement la partie la plus importante du rapport 220.

Le code `governance.py` sépare :

| Élément              | Signification                        |
| -------------------- | ------------------------------------ |
| `founder_address`    | fondateur historique                 |
| `ORG_ID`             | identité permanente                  |
| `legal_owner`        | propriétaire juridique technique     |
| `controller_address` | personne qui administre actuellement |
| Genesis              | constitution historique              |

**C'est-à-dire :**

Avant :

```text
ORG
 │
 └── founder = A
       ↓
    A contrôle tout
```

Après :

```text
ORG_ID
  │
  ├── Genesis historique
  │      └── founder = A
  │
  ├── LEGAL_OWNER = A
  │
  └── CONTROLLER = B
```

Et si l'ORG est vendue :

```text
LEGAL_OWNER A
       ↓ SALE
LEGAL_OWNER B
```

Mais :

```text
ORG_ID = identique
Genesis = identique
founder = A
```

C'est une distinction architecturale correcte.

---

# 5. Le test E2E confirme réellement ce comportement

Je ne me suis pas limité au rapport.

Le fichier `tests/test_e2e220_org_governance.py` teste notamment :

* création d'une ORG ;
* ancrage du hash ;
* absence des membres dans le bloc public ;
* absence de `genesis_body` ;
* bloc à récompense nulle ;
* interdiction aux agents ;
* transfert A → B ;
* conservation de l'ORG_ID ;
* conservation du fondateur ;
* changement du contrôleur ;
* changement du propriétaire lors d'une `SALE` ;
* `DIRECTOR_CHANGE` sans changement de propriétaire ;
* transfert de groupe sans déplacement de l'ORG ;
* succession ;
* rotation de clé ;
* annulation ;
* refus ;
* révocation des anciens droits.

Donc là, nous avons une chaîne de preuve beaucoup plus solide :

```text
spécification
     ↓
code
     ↓
test automatisé
     ↓
script live
     ↓
mesure OVH1
```

---

# 6. Le test live n'est pas seulement une simulation locale

Le script `run_live220_org_governance.py` se connecte réellement à :

```text
OVH1 : 152.228.144.34:8443
```

et interroge :

* `/health`
* `/api/v1/authz/replication`
* `/api/v1/authz/domains`
* `/api/v1/chain`
* création d'ORG
* création de wallets temporaires
* login humain
* tentative agent
* transfert
* acceptation
* export
* autres nœuds.

Le script ne se contente donc pas de faire :

```python
assert function(...)
```

Il fait réellement :

```text
machine locale
      ↓ SSH
OVH1
      ↓ HTTPS
ARTCB réel
      ↓
création wallet
      ↓
login
      ↓
création ORG
      ↓
bloc public
      ↓
SALE
      ↓
acceptation B
      ↓
vérification des autres nœuds
```

C'est beaucoup plus intéressant.

---

# 7. Ce que le live 220 démontre réellement

Le rapport donne pour la mesure du **5 septembre 2026 à 13:24:31 UTC** :

| Nœud | SHA       | commitment | transfert |
| ---- | --------- | ---------: | --------: |
| OVH1 | `9a53668` |          1 |         1 |
| OVH2 | `9a53668` |          0 |         0 |
| AWS3 | `9a53668` |          0 |         0 |
| OVH4 | `9a53668` |          0 |         0 |

et les quatre sont indiqués comme `certified_distributed_mainnet=true`.

Le scénario humain réel est également rapporté comme :

```text
création ORG             → 200
commitment                → true
unique_human_proven       → false
node_owns_domain          → false

SALE Aline → Bob
propose                   → 200
accept                    → 200

ancien contrôleur export  → 403
nouveau contrôleur export → 200
```

### Mais attention à une nuance capitale

Je **ne peux pas prétendre avoir lu le fichier brut** :

```text
logs/220_live_20260905T132431Z.json
```

car ce fichier n'est pas présent dans l'arborescence GitHub consultable : `logs/` contient actuellement surtout des artefacts historiques et `.gitkeep`, pas ce JSON live 220.

Donc :

> **J'ai vérifié le code, le test, le script live et le commit Git. Les résultats live eux-mêmes sont corroborés par le rapport 220 et par le commit qui enregistre ces mesures, mais je ne vais pas te dire que j'ai lu le JSON brut 220 alors qu'il n'est pas versionné dans GitHub.**

C'est précisément la différence entre une **preuve primaire** et une **preuve rapportée**.

---

# 8. Le problème le plus important que je trouve : les trois autres nœuds ne possèdent pas encore le tip

C'est le point que je considère actuellement comme **le principal problème technique de cette étape**.

Le système a fait :

```text
OVH1
  │
  ├── DOMAIN_COMMITMENT
  └── ORG_CONTROL_TRANSFER
```

mais :

```text
OVH2
AWS3
OVH4
```

n'ont pas encore ces deux blocs.

Le rapport le dit explicitement : les deux nouveaux blocs publics sont présents sur OVH1 seulement ; les trois autres n'ont pas encore étendu leur tip.

### C'est-à-dire ?

On a actuellement :

```text
                 GLOBAL CHAIN
                     │
                     │ ancienne chaîne commune
                     │
              ┌──────┴──────┐
              │             │
            OVH1          OVH2/AWS3/OVH4
              │             │
          + 2 blocs       ancien tip
```

Ce n'est **pas** un wipe.

Ce n'est pas non plus encore une démonstration de réplication distribuée complète.

### Pour moi :

**V-01 : partiellement démontré.**

La création du bloc public fonctionne.

La propagation P2P à tous les nœuds n'est pas encore démontrée.

---

# 9. Et cela rejoint directement le problème des Genesis que nous étudiions

Le code actuel dit quelque chose de très clair :

> le domaine est hébergé sur un ou plusieurs nœuds autorisés, mais sa simple création sur OVH1 ne signifie pas que tous les nœuds possèdent son corps Genesis.

Le `DOMAIN_BODY` est prévu comme :

```text
org_domain_nodes
```

et non :

```text
all_consensus_nodes
```

alors que le hash est :

```text
all_consensus_nodes
```

Donc ton architecture devient :

```text
                         ARTCB GLOBAL
                              │
                     HASH / COMMITMENT
                              │
               ┌──────────────┴──────────────┐
               │                             │
          ORG Genesis                    GROUP Genesis
          privé                          privé
               │                             │
        nœuds autorisés                nœuds autorisés
               │                             │
          membres / règles              membres / règles
               │
          documents privés
```

C'est exactement la séparation qu'il faut pour un système **multi-tenant**.

---

# 10. Mais j'ai trouvé un problème de confidentialité qu'il faut traiter

Il est plus subtil.

Le bloc `DOMAIN_COMMITMENT` est relativement minimal.

Mais le bloc `ORG_CONTROL_TRANSFER` contient publiquement :

```text
old_controller
new_controller
legal_owner_after
reason
```

Le code le fait explicitement.

Donc le réseau public peut savoir :

```text
ORG X
   ↓
ancien contrôleur = A
nouveau contrôleur = B
raison = SALE
```

### C'est-à-dire ?

Le contenu de l'entreprise reste privé.

Mais **la gouvernance de l'entreprise devient observable publiquement**.

Cela peut être volontaire.

Mais il faut que ce soit une décision explicite.

Pour une organisation publique, ce peut être très bien.

Pour une entreprise privée, une association sensible ou une structure familiale, cela peut être excessif.

### Je recommande plutôt :

```text
public :

ORG_ID
transfer_id
event_type
hash(previous_authority)
hash(new_authority)
reason_code éventuellement
timestamp
```

et conserver les identités complètes dans le domaine autorisé.

Ou alors :

```text
old_controller_key_id
new_controller_key_id
```

avec des identifiants cryptographiques non directement corrélables à l'identité réelle.

---

# 11. Deuxième problème : le hash seul ne garantit pas automatiquement la confidentialité

C'est un point cryptographique important.

ARTCB utilise :

```text
SHA-256(canonical Genesis)
```

C'est très bien pour l'intégrité.

Mais imaginons un Genesis extrêmement prévisible :

```json
{
  "name": "Entreprise ABC",
  "founder": "...",
  "type": "SARL"
}
```

Un attaquant peut essayer :

```text
Genesis candidat 1
       ↓ SHA-256
hash ?
       ↓
égalité ?
```

Si l'espace de recherche est petit, il peut découvrir le contenu.

Donc :

> **hash ≠ chiffrement.**

C'est fondamental.

Je recommande donc, pour les Genesis privés sensibles :

```text
commitment =
SHA-256(
    random_salt
    ||
    canonical_genesis
)
```

Le `salt` est aléatoire et suffisamment long.

Ainsi, connaître le hash public ne permet plus de faire simplement une recherche par dictionnaire sur le Genesis.

---

# 12. Troisième problème : `threshold=1`

Le code prévoit déjà :

```text
threshold
guardians
```

mais le rapport indique :

```text
threshold = 1
```

et le multisig 3-of-5 n'est pas implémenté.

Cela signifie actuellement :

```text
A
│
└── propose SALE
        ↓
       B
        ↓
     accepte
        ↓
      terminé
```

Il n'y a pas encore :

```text
A
│
├── guardian 1
├── guardian 2
├── guardian 3
├── guardian 4
└── guardian 5
       ↓
   3 signatures
       ↓
   validation
```

Pour un véritable contrôle d'organisation sur mainnet, je considère le `threshold=1` comme **insuffisant pour les organisations à forte valeur**.

---

# 13. Quatrième problème : aucun délai de contestation

Actuellement :

```text
PROPOSE
   ↓
ACCEPT
   ↓
FINALIZED
```

Il n'y a pas encore :

```text
PROPOSE
   ↓
TIMelock
   ↓
contest period
   ↓
FINALIZE
```

Le rapport le confirme.

### Scénario d'attaque

Supposons qu'une clé de contrôleur soit compromise.

L'attaquant fait :

```text
09:00 → SALE vers sa clé
09:01 → acceptation
09:01 → contrôle transféré
```

Sans délai, l'organisation peut être immédiatement détournée.

Avec un timelock :

```text
09:00 → proposition
09:00 → événement public
09:00 → notification
09:00 → début délai
       ↓
       contestation possible
       ↓
12:00 → finalisation
```

La fenêtre donne le temps de réagir.

---

# 14. Cinquième problème : `SALE` ne prouve absolument pas la vente juridique

Le code fait :

```text
SALE
   ↓
LEGAL_OWNER = nouveau contrôleur
```

Mais le protocole ne vérifie pas :

```text
contrat de vente
notaire
registre du commerce
tribunal
autorité administrative
etc.
```

Le rapport le reconnaît lui-même.

Donc il faut être extrêmement précis :

> **ARTCB prouve qu'une clé autorisée a effectué un transfert cryptographiquement valide.**

Il ne prouve pas :

> « la loi française considère Bob comme propriétaire de cette société ».

Ce sont deux choses totalement différentes.

---

# 15. Scénarios que je recommande maintenant de tester

## Scénario A — propagation normale

```text
OVH1 crée ORG
      ↓
DOMAIN_COMMITMENT
      ↓
P2P
      ↓
OVH2
AWS3
OVH4
```

Résultat attendu :

```text
4/4 voient le même bloc
4/4 voient le même hash
4/4 ont le même block hash
4/4 convergent sur le même tip
```

**C'est le test prioritaire.**

---

## Scénario B — panne OVH1 immédiatement après création

```text
OVH1 crée ORG
       ↓
bloc public
       ↓
OVH1 tombe
```

Question :

> Les autres nœuds ont-ils déjà le commitment ?

Si oui :

```text
la preuve survit à la disparition du créateur.
```

Si non :

```text
la preuve dépend encore temporairement du nœud créateur.
```

---

## Scénario C — transfert puis panne

```text
A
 ↓
SALE
 ↓
B accepte
 ↓
OVH1 tombe
```

Il faut vérifier que les autres nœuds savent finalement :

```text
ORG_ID = identique
founder = A
legal_owner = B
controller = B
```

---

## Scénario D — double transfert concurrent

Très important.

```text
A → B
A → C
```

quasi simultanément.

Le protocole doit produire **un seul état canonique**.

Sinon :

```text
OVH1 → B
OVH2 → C
```

et là nous avons une divergence de gouvernance.

C'est beaucoup plus grave qu'une simple divergence de données.

---

## Scénario E — tentative de transfert par ancien contrôleur

Après :

```text
A → B
```

A tente :

```text
A → C
```

Résultat obligatoire :

```text
403
```

et surtout :

```text
aucun bloc de transfert valide
aucune modification d'autorité
```

---

## Scénario F — agent compromis

```text
A
 │
 └── Agent A
        ↓
      SALE
```

Résultat :

```text
403
```

Le code et les tests couvrent déjà cette règle.

---

# 16. Mon verdict global sur le rapport 220

| Élément                                  | État                                |
| ---------------------------------------- | ----------------------------------- |
| Hash Genesis public                      | **Implémenté**                      |
| Genesis complet public                   | **Non — correctement évité**        |
| Bloc `reward=0`                          | **Implémenté**                      |
| ORG_ID immuable                          | **Implémenté/testé**                |
| Founder historique conservé              | **Implémenté/testé**                |
| Controller transférable                  | **Implémenté/testé**                |
| Legal owner séparé                       | **Implémenté/testé**                |
| Agent interdit                           | **Implémenté/testé**                |
| Group/subgroup séparés de l'ORG          | **Implémenté/testé**                |
| Live OVH1                                | **Mesuré**                          |
| 4 nœuds avec même code                   | **Oui au moment du live**           |
| Commitment propagé aux 4 nœuds           | **Non démontré / actuellement non** |
| Multisig                                 | **Non**                             |
| Timelock                                 | **Non**                             |
| Contestation                             | **Non**                             |
| Preuve juridique externe                 | **Non**                             |
| Réplication automatique du Genesis privé | **Non**                             |
| Chiffrement au repos                     | **Non**                             |
| Raw live JSON versionné                  | **Non trouvé**                      |

---

# 17. Conclusion critique

### Ce qui est bon

La direction architecturale est maintenant **nettement plus propre** :

```text
Genesis = constitution
      ≠
Authority = contrôle actuel
      ≠
Legal ownership = propriété
      ≠
Controller = administrateur
      ≠
Public commitment = preuve publique
```

C'est une séparation saine.

Et surtout :

> **le Genesis n'est plus traité comme une clé magique que l'on transfère.**

On conserve son identité historique et on modifie l'autorité par des opérations gouvernées.

### Ce qui bloque encore une certification forte

Le point critique n'est désormais plus tellement :

> « Est-ce que le code sait créer un commitment ? »

**Oui.**

La vraie question devient :

> **« Est-ce que ce commitment et son nouvel état d'autorité convergent réellement et définitivement sur tous les nœuds ? »**

Et là, **non, ce n'est pas encore démontré**.

Les trois nœuds n'ont pas encore reçu les deux nouveaux blocs au moment de la mesure.

Donc je classerais cette étape :

**Implémentation : forte**
**Test local/E2E : forte**
**Test live mono-nœud : démontré**
**Convergence P2P 4 nœuds : non démontrée**
**Gouvernance haute sécurité : incomplète**
**Certification mainnet définitive : non levée**

Le prochain audit pertinent n'est donc **pas de refaire le rapport 220**. Il faut maintenant lancer un **audit 221 de convergence réelle du `DOMAIN_COMMITMENT` + `ORG_CONTROL_TRANSFER` sur les 4 nœuds**, puis tester les scénarios de concurrence, panne, reprise et double transfert. C'est celui qui permettra de savoir si l'architecture passe réellement de **« fonctionnalité qui fonctionne sur OVH1 »** à **« état de gouvernance distribué et convergent du réseau »**.
