# Rapport 217 — Domaines ORG/GROUP, ancrage par hash, CAN_I (4 septembre 2026)

**Live au bootstrap :** SHA `5b1e2216dee21328c1d4e4cc8a820bfb94e3096e` sur OVH1. Ce SHA **n’inclut pas** encore 216/217. Après merge `main` + follow-main, le SHA live doit devenir celui de ce commit.

**Décision :** aucune D-0xx. Consensus / supply / PoL **inchangés**. Pas de wipe `blocks.jsonl`.

---

## 0. La distinction qu’il fallait coder (pas seulement écrire)

Il n’y a **pas** « un Genesis » unique pour tout.

| Objet | Rôle | Où ça vit | Tous les nœuds ? |
|---|---|---|---|
| **Global Genesis** | Constitution ARTCB (consensus, supply, PoL) | Chaîne / protocol | **Oui**, copie identique |
| **ORG Genesis** | Constitution de l’organisation (qui gouverne, quelles actions, plafond agent) | Fichier domaine local `data/authz/orgs.json` | **Non** le corps. **Oui** le `content_hash` |
| **GROUP Genesis** | Constitution du groupe (parent ORG, limites de délégation) | `data/authz/group_genesis.json` | **Non** le corps. **Oui** le hash |
| **PolicyTx** | GRANT / REVOKE / DENY évolutifs | `data/authz/policies.jsonl` | Domaine ORG, pas le P2P public |
| **Resource privée** | Document X, RH, R&D | graphe + bloc `visibility=private/group` | **Jamais** via P2P (`visibility≠public` rejeté) |
| **User domain** | identité, wallets, mandats agent | pas un Genesis blockchain | propriétaire |

C’est-à-dire : créer ORG A depuis une machine **n’envoie pas** les documents de A à Internet. Ça crée une constitution locale et publie **un hash**.

---

## 1. Avant / après

### 1.1 « Un groupe = un fichier JSON local »

**Avant :** `GroupManager.create_group()` écrivait `data/groups/g_xxx.json`. Pas de constitution, pas de hash, pas de parent ORG.  
C’est-à-dire : le groupe n’existait que sur **ce** serveur. Les autres nœuds ne pouvaient ni le vérifier ni savoir qu’il existait, sauf s’ils lisaient un `group_id` collé dans un bloc.

**Après :** à la création (session obligatoire) :

1. le JSON membres reste local (domaine groupe) ;
2. un **GROUP Genesis** (constitution) est signé par l’identité de session et hashé ;
3. une ligne `commitments.jsonl` contient `{kind, domain_id, content_hash, parent_id}` — **pas** la liste des membres.

C’est-à-dire : le réseau peut prouver « GROUP C existait avec cette constitution » sans connaître C1, C2, C3.

### 1.2 Genesis = base de permissions ?

**Avant (idée initiale) :** coller `A3 → READ → C` dans le Genesis.  
C’est-à-dire : pour révoquer A3, il faudrait modifier une constitution immuable.

**Après (inchangé depuis 216, formalisé en 217) :** Genesis = **qui peut déléguer**, **quelles actions existent**, **ADMIN_ORG interdit aux groupes**. Les droits concrets restent des GRANT/REVOKE.

C’est-à-dire : constitution ≠ annuaire.

### 1.3 Tous les nœuds ont-ils le contenu ?

**Avant :** confusion. Les blocs `private` étaient **sur le disque de chaque nœud qui minait/stockait**, et `GET /chain` les servait à tout le monde.

**Après, deux couches :**

- **API HTTP** (216) : `authorize()` filtre. Un anonyme ne lit plus le privé.
- **P2P** (déjà vrai, maintenant **testé** T-E44) : `get_public_blocks()` et `import_public_blocks()` refusent `visibility≠public`.
- **Commitments** (217) : `GET /authz/commitments` ne contient ni `members` ni `join_code` ni texte de document.

C’est-à-dire : un nœud global **peut** connaître `org_id` + `content_hash`. Il **ne** reçoit **pas** Document X par gossip.

Le disque d’un nœud qui a **créé** le privé le voit encore en clair (P-216-2 / P-217-1 chiffrement au repos : **non fait**).

### 1.4 `actor_address` sur les mutations de groupes

**Avant :** `POST /groups` croyait `founder_address`. `approve` / `dissolve` / `role` croyaient `actor_address`.  
C’est-à-dire : « je te crois » sans session.

**Après :** `_require_actor()` — session / clé API uniquement. Body différent de la session → 403. Sans session → 401.

C’est-à-dire : créer un groupe, c’est « je suis connecté en tant que C3 », pas « j’écris l’adresse de C3 ».

### 1.5 L’agent qui demande ses droits

**Avant :** l’agent devait tenter l’action et voir.  
**Après :** `POST /authz/can-i` → `{ effect, reason, proof: { delegation, parent, policy_version } }`.

C’est-à-dire : Agent-A3-01 peut demander `CAN_I(READ, doc-x)` **avant** de démarrer. Sans mandat agent : DENY même si A3 a le READ. Avec mandat + plafond humain : ALLOW.

---

## 2. Matrice de réplication (codée)

`GET /api/v1/authz/replication` expose `REPLICATION_MATRIX` (`src/artcb/authz/domains.py`).

| Information | Nœud consensus | Domaine ORG | Domaine GROUP | Utilisateur C3 |
|---|---|---|---|---|
| Global Genesis | plein | plein | plein | via protocole |
| Hash ORG A Genesis | oui | oui | oui | oui |
| Corps ORG A Genesis | non (sauf nœud du domaine) | oui | non | non |
| Hash GROUP C | oui | oui | oui | oui |
| Membres GROUP C | **non** | si nœud ORG | oui | si membre |
| GRANT A3→doc-x | **non** P2P | domaine | domaine | si sujet/issuer |
| Document X | **non** P2P | fichier local du nœud qui l’a gravé | idem | si `authorize` ALLOW |

---

## 3. Fichiers

| Fichier | Rôle |
|---|---|
| `src/artcb/authz/domains.py` | matrice + `canonical_hash` + commitment public |
| `src/artcb/authz/genesis.py` | OrgGenesis, GroupGenesis, CommitmentLog |
| `src/api/authz_routes.py` | `/commitments`, `/replication`, `/can-i` |
| `src/api/groups_routes.py` | session obligatoire + genesis à la création |
| `tests/test_e2e217_domain_genesis.py` | T-E44 |

---

## 4. Matrice protocole

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| 4 Genesis distincts | proposition 217 | audit collé | `domains.py` `genesis.py` | T-E44 | après follow-main |
| Hash public, corps privé | proposition 217 | | `CommitmentLog` | T-E44 | après |
| P2P ≠ privé | déjà code | | `p2p/sync.py` | T-E44 | déjà live (public only) |
| Mutations groupes authentifiées | proposition 217 | 216 P-216-3 | `_require_actor` | T-E44 + groups | après |
| CAN_I agent | 213 + 217 | | `/authz/can-i` | T-E44 | après |
| Chiffrement au repos | **non** | 211 | non | — | non |

---

## 5. Ce qui reste (honnête)

- **P-217-1** Les graphes `private` restent en clair sur le disque du nœud qui les a gravés.
- **P-217-2** Les commitments ne sont pas encore un *bloc* public ancré dans `blocks.jsonl` (journal domaine, pas un `append_block`). C’est-à-dire : la preuve d’existence est locale + API ; elle n’est pas encore une hauteur de chaîne globale. Prochaine étape possible : un bloc `visibility=public` dont `public_symbols` = `{kind, id, content_hash}` uniquement.
- **P-217-3** Réplication du *corps* ORG vers d’autres nœuds « du domaine » : pas implémentée. Aujourd’hui 1 nœud = le domaine. Les 4 nœuds officiels restent un consensus **global**, pas 4 copies de ORG A.
- **P-217-4** Signature cryptographique du fichier Genesis (Ed25519/ML-DSA) : l’identité vient de la session, le hash est déterministe, le fichier n’est pas encore un objet signé autonome.

Je ne dis **pas** : « ORG A est un shard privé répliqué seulement chez A ». Je dis : « le protocole **distingue** maintenant existence (hash) et contenu (domaine), et le P2P ne transporte toujours que le public. »
