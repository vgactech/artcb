# CREATOR RIGHTS CHARTER — ARTCB Blockchain

**Version :** 1.0  
**Date :** 2026-08-04  
**Statut :** Document fondateur — gravé dans le genesis block (index 0)  
**Contact :** official@artcb.space

---

## 1. Qui est le créateur ?

ARTCB est une blockchain créée et maintenue par son fondateur (ci-après **"le Créateur"**).

L'adresse publique du Créateur est gravée dans le genesis block (bloc index 0) de la blockchain.
Elle est **permanente et ne peut jamais être modifiée** par aucun vote, aucune proposition, aucune mise à jour de code.

---

## 2. Droits permanents du Créateur

Ces droits sont **immuables**. Ils sont inscrits dans le genesis block et dans le code source.
Aucun vote communautaire ne peut les modifier ou les supprimer.

| Droit | Valeur | Description |
|-------|--------|-------------|
| **Veto absolu** | Activé | Un vote NON du Créateur rejette toute proposition, quelle que soit la majorité |
| **Poids de vote** | 999 999 voix | 1 vote Créateur = 999 999 votes ordinaires |
| **Validation immédiate** | Activé | Un vote OUI du Créateur accepte toute proposition immédiatement |
| **Modification du code** | Libre | Le Créateur peut modifier le code source à tout moment |
| **Droits non révocables** | Oui | Ces droits ne peuvent pas être révoqués par la communauté |

---

## 3. Objectif à long terme — ce qui ne changera JAMAIS

Le Créateur s'engage à maintenir ces règles pour toujours :

| Règle immuable | Valeur | Raison |
|---|---|---|
| **Supply max ARTCB** | 21 000 000 ARTCB | Hard cap économique — équité garantie |
| **Algorithme Proof-of-Learning** | PoL collectif | Mécanisme de consensus unique ARTCB |
| **Seuil PoL minimum** | 0.6 | Qualité des blocs garantie |
| **Cryptographie post-quantique** | ML-DSA-65 FIPS204 | Sécurité à long terme contre les ordinateurs quantiques |
| **Contrôle utilisateur** | Clés privées = propriété de l'utilisateur | Vos données vous appartiennent |
| **Mission** | Construire la nouvelle internet + blockchain adaptée à l'IA | Objectif fondateur |

---

## 4. Ce que cela signifie pour vous (utilisateurs)

### Vos garanties

- **Vos clés privées vous appartiennent** — personne, pas même le Créateur, ne peut accéder à vos données privées sans votre clé
- **Vos blocs sont permanents** — un bloc validé ne peut jamais être effacé
- **Les règles économiques sont fixes** — supply max, halving, rewards PoL ne changeront pas
- **La cryptographie est moderne** — ML-DSA-65 résistant aux ordinateurs quantiques

### Ce que le Créateur peut faire

- Modifier le code (corrections, nouvelles fonctionnalités)
- Valider ou rejeter toute proposition de gouvernance
- Fixer les paramètres de configuration (ports, intervalles, etc.)

### Ce que le Créateur ne fera PAS

- Accéder à vos clés privées ou données privées
- Modifier les règles économiques fondamentales (supply, PoL)
- Vendre ou transférer les droits de créateur sans annonce publique
- Utiliser le veto de façon abusive contre les intérêts de la communauté

---

## 5. Gouvernance — comment fonctionne le vote

Pour les mises à jour majeures (changement de règles PoL, tokenomics, ACL) :

1. **Le Créateur publie une proposition** `GOV-YYYY-MM-DD-NNN`
2. **Vote ouvert pendant 14 jours** — 1 wallet = 1 voix ordinaire
3. **Résultat** :
   - Majorité OUI → mise à jour maintenue
   - Majorité NON → rollback ou correctif par le Créateur
   - Vote NON du Créateur → veto absolu, proposition rejetée
   - Vote OUI du Créateur → acceptation immédiate

**Ce qui ne peut PAS être soumis au vote :**
- Les droits du Créateur (veto, poids de vote, adresse)
- La supply maximale de 21 000 000 ARTCB
- L'algorithme Proof-of-Learning collectif

---

## 6. Comparaison avec d'autres blockchains

| Blockchain | Contrôle fondateur | Position ARTCB |
|---|---|---|
| Bitcoin | Zéro (Satoshi est parti) | Plus protégé |
| Ethereum | Vote off-chain (EIP), Vitalik influent mais pas de veto | Plus protégé |
| Cosmos | 33.4% des tokens = veto possible | Comparable (ARTCB = veto explicite) |
| BNB Chain | Binance contrôle les validateurs | Similaire mais ARTCB est plus transparent |

**Philosophie ARTCB :** Le Créateur est le garant à long terme de la vision. La communauté est respectée et consultée. Les deux coexistent de façon transparente.

---

## 7. Vérification publique

N'importe qui peut vérifier les droits créateur en lisant le genesis block :

```bash
# Lire le genesis block
python3 -c "
import json
from pathlib import Path
genesis = json.loads(Path('data/chain/blocks.jsonl').read_text().split('\n')[0])
cr = genesis['creator_rights']
print('Créateur :', cr['creator_wallet'][:40], '...')
print('Veto     :', cr['creator_veto_enabled'])
print('Poids    :', cr['creator_vote_weight'])
print('Immutable:', cr['creator_rights_immutable'])
"
```

Ou via l'API :
```
GET /api/v1/chain/genesis
```

---

## 8. Contact et transparence

Toutes les décisions importantes du Créateur sont annoncées publiquement :
- Dans le CHANGELOG du dépôt GitHub
- Via l'email official@artcb.space
- Dans les propositions de gouvernance `GOV-*`

**© 2026 ARTCB — official@artcb.space**  
*Ce document est public et commité sur GitHub. Il fait partie du protocole ARTCB.*
