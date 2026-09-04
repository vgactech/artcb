# Rapport 216 — Privacy Enforcement & Authorization (4 septembre 2026)

**Objet :** première couche réelle du moteur d’autorisation ARTCB (P0), distincte de l’egress 215.

**Live au bootstrap de cette tâche :** SHA `5b1e2216dee21328c1d4e4cc8a820bfb94e3096e` sur OVH1 (`https://152.228.144.34:8443`), `health_http=200`, PQC ML-DSA-65. Ce rapport **n’est pas** une preuve live : le code n’est pas déployé tant que `origin/main` n’a pas absorbé le commit et que `artcb-follow-main.timer` n’a pas tiré.

**Décision opérateur :** aucune D-0xx ajoutée. Ceci est une **proposition + code + tests**. Consensus (PoL / hash de bloc) **inchangé**.

---

## 0. Ce qu’il faut comprendre en une phrase

Avant, ARTCB **classait** les données (`private` / `group` / `public`) et vérifiait parfois « es-tu membre de ce groupe ? ».  
Après, ARTCB **décide** « cet acteur a-t-il le droit de **lire cette ressource** ? » — et refuse (404) si non.

C’est-à-dire : `visibility=private` n’est plus un autocollant. C’est une classification lue par un moteur `authorize()`. Sans identité prouvée + permission, la donnée n’est pas renvoyée.

---

## 1. Avant / après, point par point (avec « c’est-à-dire »)

### 1.1 `GET /graph/{graph_id}`

| | |
|---|---|
| **Avant** | Le serveur chargeait le graphe et le renvoyait. |
| **C’est-à-dire** | Connaître l’identifiant suffisait. Un bloc `private` gravé était lisible par n’importe qui qui avait le `graph_id` (ou qui le devinait / le lisait dans `GET /chain`). |
| **Après** | `authorize(acteur, READ, graphe)`. Si le graphe est gravé `private`/`group` et que l’acteur n’est ni propriétaire, ni membre autorisé, ni titulaire d’un GRANT : **404**. |
| **C’est-à-dire** | On ne dit même pas « interdit » : on dit « introuvable », pour ne pas révéler qu’un document privé existe. |

Exception volontaire : un graphe **pas encore gravé** (juste `POST /encode`) reste lisible par `graph_id`. C’est-à-dire : c’est un brouillon local, un jeton de capacité, pas encore une ressource organisationnelle. Dette : P-216-1.

### 1.2 `GET /chain` et `GET /chain/blocks`

| | |
|---|---|
| **Avant** | `list_blocks(visibility=..., group_id=...)` filtrait **si le client demandait un filtre**. Sans filtre, **tous** les blocs partaient, y compris `private`. |
| **C’est-à-dire** | `group_id` était un critère de *recherche*, pas une *autorisation*. Demander `?group_id=C` ne prouvait pas que vous aviez le droit de voir C. Ne pas demander de filtre montrait tout. |
| **Après** | La liste est filtrée par `authorize()` **après** le filtre de sélection. Un anonyme ne voit que le `public`. Un membre de A ne voit pas les blocs de C. Un GRANT A3→Document X fait apparaître **ce** bloc, pas Y. |

`GET /chain/status` et `GET /chain/verify` restent des métadonnées de **consensus** (hauteur, hash, validité). C’est-à-dire : savoir qu’il y a N blocs n’est pas la même chose que lire le texte du document C3.

### 1.3 `GET /chain/block/{index}`

| | |
|---|---|
| **Avant** | Lecture directe du JSON du bloc. |
| **C’est-à-dire** | L’index était une clé d’accès. |
| **Après** | 404 si l’acteur n’est pas autorisé. |

Même logique sur `GET /api/v1/ai/memo/{index}`, `GET /chain/search`, `GET /chain/export`, `GET /ai/memory`, `POST /search`, `GET /node/{id}` (quand le nœud IR appartient à un graphe).

### 1.4 `POST /store` et `actor_address`

| | |
|---|---|
| **Avant** | Pour `visibility=group`, le serveur croyait `body.actor_address`. |
| **C’est-à-dire** | Un client pouvait écrire `"actor_address": "<adresse du fondateur>"` sans posséder le wallet, et graver dans le groupe. |
| **Après** | L’identité vient d’une **session** `sess_`, d’une **clé API** `artcb_` liée au wallet, ou d’un **wallet déchiffré** (`wallet_name` + mot de passe). Si `actor_address` est présent et **différent** : 403 `actor_address_mismatch`. Sans identité, un store `group` : **401**. |
| **C’est-à-dire** | Le JSON n’est plus une preuve. C’est au mieux une confirmation qui doit coller à l’identité réelle. |

### 1.5 Moteur GRANT / REVOKE (le scénario A3 → C3)

| | |
|---|---|
| **Avant** | Un membre avait `address + role + joined_at`. Pas de `subject / resource / action / expiration / révocation`. |
| **C’est-à-dire** | On ne pouvait **pas** dire « A3 a le droit de lire Document X de C3/Sub2, et seulement ça ». Soit A3 était membre de C (trop large), soit il n’était pas membre (trop étroit). |
| **Après** | Des transactions de politique versionnées (`PolicyTx`) : GRANT, DENY, REVOKE. Le Genesis d’organisation (`POST /api/v1/authz/orgs`) est la **constitution** (qui gouverne, DENY>ALLOW, plafond agent). Il **ne** stocke **pas** « A3 peut lire C3 ». |
| **C’est-à-dire** | On peut accorder aujourd’hui et révoquer demain **sans réécrire le Genesis**. |

Règle d’évaluation :

- un DENY qui matche gagne toujours (DENY > ALLOW) ;
- un GRANT sur `resource_id=doc-x` ne couvre pas `doc-y` ;
- un membre du groupe parent C n’hérite **pas** de Sub2 (least privilege sur l’arbre) ;
- un agent (`X-ARTCB-Agent-Id`) n’hérite **pas** de la membership humaine : il lui faut son propre GRANT, **et** le humain doit encore être autorisé (plafond).

### 1.6 Sous-groupes

| | |
|---|---|
| **Avant** | Groupes plats. |
| **Après** | `POST /api/v1/groups/{id}/subgroups` crée un groupe avec `parent_group_id`. Les documents peuvent porter `subgroup_id` + `resource_id` dans un **index sidecar** (`data/authz/resources.jsonl`), **hors hash de bloc**. |
| **C’est-à-dire** | L’autorisation n’est pas le consensus. On n’a pas changé le calcul du hash. On a ajouté une couche à côté. |

### 1.7 Explorer / P2P

| | |
|---|---|
| **Avant** | `GET /chain/explorer` renvoyait `latest_blocks[-10:]` **sans** filtrer le privé. |
| **Après** | `latest_blocks` passe par `authorize()`. Le P2P `GET /p2p/blocks/public` ne syncait déjà que le public — inchangé, et c’est volontaire : le consensus public ≠ le droit de lire un mémo privé. |

---

## 2. Ce que Cursor 215 avait fait — et ce que 216 ajoute

215 a corrigé **les sorties** (egress, webhooks, LLM, `/wallet/list`).  
216 corrige **l’entrée en lecture des données persistées**.

Ce n’est pas la même couche. Les deux sont nécessaires. Ni l’une ni l’autre ne chiffre les graphes au repos (P-216-2).

---

## 3. Fichiers

| Fichier | Rôle |
|---|---|
| `src/artcb/authz/engine.py` | DENY>ALLOW, membership implicite, plafond agent |
| `src/artcb/authz/store.py` | Journal GRANT/REVOKE + index ressource |
| `src/artcb/authz/genesis.py` | Constitution d’organisation |
| `src/artcb/authz/identity.py` | Identité session / API key — jamais le body |
| `src/artcb/authz/gate.py` | Pont HTTP ↔ moteur ↔ chaîne |
| `src/api/authz_routes.py` | `/api/v1/authz/orgs`, `/grants`, `/revoke`, `/decide` |
| `src/api/routes.py` | Enforcement lecture + store |
| `src/api/groups_routes.py` | Sous-groupes ; liste des groupes = identité réelle |
| `src/api/ai_routes.py` | search / export / memory / memo |
| `src/api/devnet_routes.py` | explorer `latest_blocks` |
| `src/artcb/groups/manager.py` | `parent_group_id`, `create_subgroup` |
| `tests/test_e2e216_authz_privacy.py` | T-E43 |

---

## 4. Matrice (rang protocole)

| Règle | Décidée (D-0xx) | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| `authorize()` sur lectures graph/chain/search | proposition 216 | 213-214 (concept) | `authz/`, `routes.py` | T-E43 | **non** |
| Ne pas croire `actor_address` au store | proposition 216 | audit collé | `routes.py` store | T-E43 + `test_groups` | non |
| `private` = classification, pas ACL | proposition 216 | 215 P-215 audit ouvert | engine + gate | T-E43 private 404 | non |
| GRANT A3 → C3/Sub2/Document X | proposition 216 | scénario opérateur | `PolicyStore` + routes | T-E43 A3 | non |
| REVOKE | proposition 216 | | `PolicyStore.revoke` | T-E43 | non |
| DENY > ALLOW | 213 (concept) | 213 | `engine.py` | T-E43 unitaire | non |
| Plafond agent | 213-214 P-215-5 | 213 | engine + header | T-E43 | non |
| Genesis = constitution | proposition 216 | | `genesis.py` | T-E43 create org | non |
| Données privées chiffrées au repos | **non** | 211 HE | **non** (HE inchangé) | — | non |
| Routes groupes *mutation* sans `actor_address` body | **non** (reste) | | partiel | — | non |

---

## 5. Preuves de test (T-E43)

```
pytest tests/test_e2e216_authz_privacy.py
7 passed
```

Couverture e2e216 :

1. DENY bat ALLOW (moteur pur).
2. Un agent ne dépasse pas le plafond humain.
3. C2 membre de Groupe C **ne** lit **pas** Sub2.
4. Bloc `private` : 404 anonyme, 200 propriétaire.
5. Brouillon `encode` encore lisible (working copy).
6. Spoof `actor_address` + autre wallet → 403.
7. A3 GRANT Document X : lit X, pas Y, pas C2 ; agent sans mandat 404 ; agent avec GRANT 200 ; REVOKE → 404 humain et agent.

Régression autour : `test_groups` + `test_mining_pipeline` + `test_pool_integration` + T-E42 + dashboard : **pass**.  
`test_api.py::test_wailly_demo_excerpt` échoue ici faute de `pypdf` (préexistant à cet environnement, pas à 216).

---

## 6. Dettes restantes (P-216)

- **P-216-1** Graphes non gravés : `graph_id` = jeton de capacité. Fermer si l’opérateur veut que même le brouillon exige une session.
- **P-216-2** Chiffrement au repos des graphes `private` / `group`. Aujourd’hui on **filtre** ; le fichier `data/graphs/*.json` et `blocks.jsonl` restent lisibles **sur le disque du nœud**. C’est-à-dire : un opérateur SSH voit encore le texte. Ce n’est **pas** « l’entreprise A peut utiliser ARTCB sans que son travail privé soit sur le nœud en clair ».
- **P-216-3** Mutations groupes (`approve` / `role` / `dissolve`) croient encore `actor_address` dans le body. Lecture des groupes : liste = session ; fiche groupe = projection publique sans membres si non-membre.
- **P-216-4** `POST /ir/learn` accepte encore `wallet_address` non prouvé pour les rewards (pas pour l’ACL de lecture une fois gravé `private` sans owner → illisible).
- **P-216-5** P2P : un nœud qui a déjà le JSONL local voit les blocs sur disque. Le moteur protège l’**API HTTP**. Un sync P2P ne pousse toujours que le public.
- **P-216-6** Machine à états d’identité / domaines ORG complets / preuve cryptographique de chaque GRANT (signature du grantor sur le tx) : structure prête, signature du GRANT pas encore obligatoire.
- **P-216-7** Audit 215 `groups_routes` / `privacy_routes` HE : `privacy/status` reste public (métadonnée HE, pas les vecteurs). `privacy/encrypt` n’est pas une lecture de graphe.

**Je ne certifie toujours pas** la propriété :

> « L’entreprise A peut utiliser ARTCB sans que son travail privé soit divulgué au registre public **et** chaque membre ne voit que ce qui lui est autorisé **y compris vis-à-vis de l’opérateur du nœud**. »

La seconde moitié (API) est maintenant **démontrée par T-E43**. La première (disque / opérateur / P2P nœud unique) **non**.

---

## 7. Comment utiliser le scénario A3 → C3

1. C3 se connecte (`sess_`).
2. C3 crée Groupe C, puis `POST /groups/{C}/subgroups` → Sub2.
3. C3 grave Document X : `visibility=group`, `group_id=C`, `subgroup_id=Sub2`, `resource_id=doc-x`, `wallet_name=C3`.
4. C3 `POST /authz/grants` `{ subject: A3, action: READ, resource: { resource_id: "doc-x" } }`.
5. A3 lit `GET /graph/{id}` → 200. Document Y sans GRANT → 404.
6. `POST /authz/revoke` `{ grant_id }` → A3 404.

Agent : header `X-ARTCB-Agent-Id: agent-a3-01` + GRANT `subject_kind=agent` `parent_subject=A3`. Sans ce GRANT, l’agent ne « chevauche » pas le droit humain.
