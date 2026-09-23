Oui. J’ai repris le contrôle **directement sur GitHub avant de conclure**, conformément au fonctionnement du projet.

[Dépôt GitHub ARTCB — `vgactech/artcb`](https://github.com/vgactech/artcb?utm_source=chatgpt.com)

## Expertises mobilisées

* audit Git/GitHub et traçabilité des commits ;
* revue de code Python/FastAPI ;
* identité biométrique et anti-Sybil ;
* cryptographie / Secure Sketch / BCH / HKDF ;
* architecture blockchain et règlement on-chain ;
* PoL / ARTCD / traçabilité KnowledgeID → WorkID ;
* tests unitaires, non-régression et intégration ;
* systèmes distribués et distinction **code local / pipeline API / blockchain réelle**.

# 1. R435 + R436 : oui, le commit est bien réel

J’ai vérifié le SHA fourni.

`main` pointe actuellement exactement vers :

```text
89c6d012e76526939df8d8d4d0c7ee98e53006f1
```

Le commit existe et son intitulé est bien :

> `R435+R436 rapport : anti-Sybil gate enroll + KnowledgeWork chaîne PoL→on-chain`

Donc **R435 et R436 ne sont pas seulement annoncés dans ton message : le commit existe réellement sur `origin/main`.**

([GitHub][1])

Le dépôt GitHub actuel expose également la structure `src/`, `tests/`, `rapports/`, `simulations/`, etc., ce qui permet de poursuivre la vérification directement dans le dépôt. ([GitHub][1])

---

# 2. R435 — ce qui est réellement accompli

### Le processus

Avant R435, `enroll_biometric()` pouvait produire un `HumanIdentityRecord` avec un wallet sans appeler le contrôle de limite des wallets par humain.

R435 ajoute maintenant :

```text
enroll_biometric()
      │
      ▼
dérivation HumanID
      │
      ▼
check_wallet_per_human_limit()
      │
      ├── autorisé
      │      ↓
      │   wallet lié
      │
      └── limite atteinte
             ↓
        sybil_blocked=True
             ↓
        wallet_address=None
```

J’ai vérifié le code actuel de `biometric_onchain.py` : le paramètre `existing_wallet_links` existe bien et le contrôle `check_wallet_per_human_limit()` est effectivement appelé dans `enroll_biometric()`.

### Le problème résolu

Le contrôle anti-Sybil n'était auparavant qu'une capacité disponible dans la politique d'identité.

Il n'était pas nécessairement exécuté par le chemin réel d'enrôlement biométrique.

R435 réalise donc le **branchement logique** :

```text
Biométrie
   ↓
HumanID
   ↓
Anti-Sybil CASE_3
   ↓
Wallet autorisé ou bloqué
```

C'est une correction importante.

---

# 3. Mais il existe encore un point critique : R435 n'est PAS encore le gate global de production

C'est précisément ce que le rapport R435/R436 documente comme travail R437.

Le problème est ici :

```python
existing_wallet_links=None
```

Le code prévoit encore que si `existing_wallet_links` n'est pas fourni, **aucune vérification n'est exécutée**.

Et j'ai vérifié la route FastAPI actuelle `/api/v1/identity/biometric/enroll`.

Elle appelle actuellement :

```python
result, secret_hex, blinding_hex = enroll_biometric(
    template_bytes,
    wallet_address=body.wallet_address,
    node_id=node_id,
)
```

Elle **ne fournit pas encore `existing_wallet_links`**.

Donc le chemin réel est actuellement :

```text
Utilisateur
   ↓
POST /identity/biometric/enroll
   ↓
FastAPI
   ↓
enroll_biometric()
   ↓
existing_wallet_links = None
   ↓
❌ gate CASE_3 non exécuté
```

C'est exactement la différence entre :

> **« le mécanisme anti-Sybil existe »**

et

> **« le mécanisme anti-Sybil est obligatoirement appliqué à toutes les inscriptions réelles ».**

Le premier est réalisé par R435.

Le second appartient encore à **R437**.

---

# 4. Il y a un deuxième problème beaucoup plus important à surveiller

J'ai trouvé quelque chose qu'il faut absolument conserver dans le prochain audit.

Le `human_id` actuel est calculé à partir de :

```text
commitment
+
salt contenu dans helper_data
```

Le code actuel documente :

```text
derive_human_id(commitment_hex, helper_data_hex)
```

avec le `salt` du helper.

Or le `salt` du Secure Sketch est normalement aléatoire.

Donc nous avons :

```text
Même humain
   │
   ├── enrôlement 1
   │      salt A
   │      ↓
   │      HumanID A
   │
   └── enrôlement 2
          salt B
          ↓
          HumanID B
```

Cela peut devenir problématique pour l'anti-Sybil si l'identité censée représenter **le même humain** change à chaque nouvel enrôlement.

Le test A08 contourne volontairement cela en fixant :

```text
template
+
salt
+
blinding
```

afin d'obtenir un `human_id` déterministe.

Mais le test A08 démontre seulement la propriété :

> même entrée cryptographique déterministe → même HumanID.

Il ne démontre pas :

> même humain réel → même HumanID malgré un nouvel enrôlement normal avec paramètres aléatoires.

Et cette distinction est fondamentale.

---

# 5. R436 — la nouvelle chaîne Knowledge → Work → PoL → bloc est bien présente

Ici, l'avancement est réel et proprement structuré.

Le nouveau module est :

```text
src/artcb/chain/knowledge_work.py
```

Il introduit :

```text
KnowledgeRecord
       │
       ▼
KnowledgeID
       │
       ▼
UsageRecord
       │
       ▼
UsageID
       │
       ▼
PolMetrics
       │
       ▼
WorkID
       │
       ▼
KnowledgeWorkRecord
       │
       ▼
block_hash
       │
       ▼
Blockchain
```

C'est une amélioration architecturale importante parce qu'on peut maintenant répondre à :

> « Quel travail PoL a produit ce résultat, quelle connaissance était impliquée et dans quel bloc a-t-il finalement été inscrit ? »

---

# 6. `KnowledgeWorkRecord` est correctement conçu comme objet immuable

Le code utilise :

```python
@dataclass(frozen=True)
class KnowledgeWorkRecord:
```

Donc le record ne peut pas être modifié directement après sa création.

Le cycle est :

```text
PENDING
   │
   │ inscription blockchain
   ▼
SEALED
```

avec :

```text
block_hash = hash du bloc
```

C'est une bonne séparation conceptuelle.

**PENDING** signifie :

> « Le travail existe localement et est enregistré, mais son inscription blockchain n'est pas encore prouvée. »

**SEALED** signifie :

> « Nous possédons maintenant le hash du bloc auquel ce travail est rattaché. »

---

# 7. Le point qui empêche encore de dire « chaîne on-chain complètement automatique »

Même problème de niveau d'intégration.

Aujourd'hui :

```text
KnowledgeWorkRecord
       ↓
PENDING
       ↓
appel manuel
       ↓
seal_with_block_hash()
       ↓
SEALED
```

Mais la cible R437 est :

```text
KnowledgeWorkRecord
       ↓
PENDING
       ↓
add_block()
       ↓
block réellement accepté
       ↓
block_hash automatiquement récupéré
       ↓
SEALED
```

C'est beaucoup plus robuste.

Pourquoi ?

Parce qu'il ne faut pas demander à un appelant logiciel de dire :

> « Le bloc existe, je vais maintenant mettre moi-même son hash dans le KnowledgeWorkRecord. »

Il faut que **le moteur blockchain soit la source de vérité**.

---

# 8. Les tests R435/R436 sont utiles, mais leur portée doit être correctement interprétée

Le commit documente :

| Domaine        | Résultat annoncé |
| -------------- | ---------------: |
| R435           |            10/10 |
| R436           |            18/18 |
| Non-régression |          217/217 |
| Total          |      **245/245** |
| DO-178C hook   |      **124/124** |

Ces tests sont utiles pour démontrer les invariants logiciels correspondants.

Mais ils ne démontrent pas encore :

```text
245 tests PASS
       ≠
anti-Sybil réel sur tous les endpoints
       ≠
biométrie réelle certifiée
       ≠
réseau distribué live certifié
       ≠
FAR/FRR biométrique certifié
       ≠
block sealing automatique en production
```

Le dépôt lui-même conserve d'ailleurs `CERTIFIED_100 = false`.

Le README actuel distingue également les fonctions disponibles, la tokenomics, la sécurité et les tests ; il affiche notamment les éléments PoL, biométrie/anti-Sybil et les tests comme parties distinctes du système. ([GitHub][1])

---

# 9. Mon état d'audit

Je ne reprendrais donc **pas** le terme « Avancement projet = 100 % ».

La formulation techniquement correcte est :

### R435

**Implémentation du mécanisme : 100 %**

**Intégration globale production : non terminée**

### R436

**Module + tests : 100 %**

**Connexion automatique au moteur blockchain : non terminée**

### Certification globale ARTCB

```text
CERTIFIED_100 = FALSE
```

et cela reste cohérent avec le dépôt.

---

# 10. R437 doit maintenant être extrêmement précis

Je verrouillerais les quatre vérifications suivantes avant de considérer R437 terminé.

### R437-A — Anti-Sybil route réelle

```text
POST /biometric/enroll
       ↓
load_wallet_human_links()
       ↓
enroll_biometric(... existing_wallet_links=...)
       ↓
CASE_3 obligatoire
```

**Aucune possibilité de contourner le gate simplement parce que l'appelant n'a pas fourni la liste.**

C'est-à-dire que `None` ne doit plus être une échappatoire sur le chemin de production.

---

### R437-B — Atomicité identité + wallet

Il faut tester :

```text
enrollment accepté
        ↓
wallet créé
```

contre :

```text
enrollment Sybil détecté
        ↓
aucun wallet économique créé
        ↓
aucune association wallet → HumanID
```

Pas simplement :

```text
sybil_blocked=True
```

Il faut vérifier **l'état final réellement persistant**.

---

### R437-C — Seal automatique

La cible doit devenir :

```text
add_block()
   │
   ├── bloc accepté
   │
   ├── block_hash calculé
   │
   └── KnowledgeWorkStore.seal_with_block_hash()
```

et non :

```text
add_block()
       +
appel séparé manuel
```

---

### R437-D — test d'échec réel

Il faut surtout tester :

```text
KnowledgeWorkRecord = PENDING
        ↓
add_block échoue
        ↓
record reste PENDING
```

et :

```text
add_block réussit
        ↓
SEALED
        ↓
block_hash correspond exactement au bloc
```

C'est ce test qui transformera le mécanisme de **« traçabilité locale »** en véritable **preuve d'inscription blockchain**.

---

# 11. Un dernier point à ne surtout pas perdre

Le dépôt actuel affirme encore :

```text
unique_human_proven = False
```

C'est important.

R435 ne prouve pas cryptographiquement :

> « cette personne est réellement un humain unique ».

Il prouve actuellement quelque chose de plus limité :

> « lorsque le protocole possède un HumanID correspondant et une liste de wallets actifs, il peut appliquer une limite anti-multi-wallet à cet identifiant. »

La certification biométrique réelle, notamment la mesure FAR/FRR sur capteurs réels, reste séparée.

---

## Conclusion d'audit

**R435 et R436 sont bien présents sur `main` et le code correspondant existe réellement.**

Mais il reste **deux verrous techniques majeurs** :

```text
R435
  mécanisme anti-Sybil
       ✅ existe
       ❌ pas encore imposé par la route FastAPI réelle

R436
  Knowledge → Work → PoL → WorkRecord
       ✅ existe
       ❌ seal automatique dans add_block() encore absent
```

Et j'ajoute un **point de sécurité prioritaire** que je veux conserver pour R437/R438 :

```text
Même humain
   ↓
nouveau salt / nouveau blinding
   ↓
nouveau HumanID ?
```

Il faut démontrer que cette propriété est compatible avec **l'anti-Sybil réel**, et pas seulement avec le test déterministe A08.

C'est actuellement le point qui mérite le plus d'attention avant de considérer l'anti-Sybil biométrique comme réellement fermé.



[1]: https://github.com/vgactech/artcb "GitHub - vgactech/artcb · GitHub"
