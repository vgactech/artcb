# Rapport 218 — Domain Registry : le nœud héberge, le fondateur possède (4 septembre 2026)

**Live au bootstrap de cette tâche :** SHA `586869f397c60b685678064faac3f593e4be8393` sur OVH1 (`docs(217)`).  
**Live après push `main` + follow-main (2026-09-04 23:44Z) :** SHA `ae5868f33df3613ba6011ab7a11a4b54ffe80649` sur les **4** nœuds + HTTPS OVH1 `:8443`.

**Décision :** aucune D-0xx. Consensus / supply / PoL **inchangés**. Pas de wipe `blocks.jsonl`. Pas de copie automatique du corps ORG sur les 4 nœuds officiels.

---

## 0. Ce qui a été réellement audité sur `main` (avant ce code)

`REPLICATION_MATRIX` dans `src/artcb/authz/domains.py` décrivait `org_domain_nodes` / `group_domain_nodes`. **Aucun registre ne l’exécutait.**

Concrètement, à la création :

```text
Navigateur Alice
      │  POST /api/v1/authz/orgs  (session)
      ▼
AuthzGate.genesis.create_org
      │
      ▼
data/authz/orgs.json          ← corps local au processus qui a reçu la requête
data/authz/commitments.jsonl  ← hash public, journal local (pas un bloc)
```

Il n’existait pas de `domain_id`, pas de liste de nœuds autorisés, pas d’export/import, pas de routage. « 1 nœud = le domaine » était le *fait* opérationnel, pas une propriété cryptographique.

C’est-à-dire : Alice **peut** créer une organisation sans installer ARTCB (déjà vrai en 217). Mais si le serveur disparaît, le corps Genesis n’a **aucun** chemin de récupération fondateur.

---

## 1. Avant / après

### 1.1 « Le serveur qui crée l’ORG en est propriétaire »

**Avant :** le stockage local était le seul lieu. Rien ne disait que le fondateur reste la racine de propriété si le serveur change.

**Après :** chaque ORG/GROUP émet un **Domain Manifest** :

* `domain_id`
* `founder_address` (wallet de session, jamais le `node_id`)
* `genesis_hash`
* `hosting_node_id` (infrastructure)
* `authorized_nodes`
* `storage_mode` : `artcb_managed` | `selected_nodes` | `personal` | `hybrid`
* `node_owns_domain` = **toujours `false`**

C’est-à-dire : **un nœud héberge un domaine ; il ne possède pas le domaine.**

### 1.2 Alice sans serveur

**Avant :** possible via l’API, mais le résultat n’était qu’un fichier `orgs.json` sur ce processus.

**Après :** même création (session obligatoire), plus un manifeste et un mode de stockage choisi dans l’UI `/groups`. Alice n’installe rien. Le serveur d’arrivée est l’hôte initial, pas le propriétaire.

### 1.3 Récupération / migration

**Avant :** copier `orgs.json` à la main. Aucune vérif de hash, aucune preuve fondateur.

**Après :**

```text
POST /authz/domains/{id}/export   → session fondateur uniquement
POST /authz/domains/import        → session fondateur + SHA-256(corps) == genesis_hash
```

Un corps altéré est rejeté (`422 genesis_hash_mismatch`). Bob ne peut pas exporter le domaine d’Alice (`403`).

C’est-à-dire : la migration n’est **pas** « copier le fichier ». C’est une autorisation fondateur + contrôle du hash.

### 1.4 Les 4 nœuds officiels reçoivent-ils le corps ?

**Non.** Créer ORG A sur le nœud A n’écrit rien sur le nœud B. Le test T-E45 démarre deux processus (`node-a`, `node-b`) : B a `count=0` jusqu’à l’import fondateur.

Ajouter un réplica (`POST /domains/{id}/replicas`) enregistre une **intention**. `body_copied=false`. Ce n’est pas une copie P2P.

### 1.5 Le commitment est-il un bloc blockchain ?

**Toujours non** (P-217-2 / P-218-2). Le manifeste et le hash restent dans `domains.json` + `commitments.jsonl` **locaux**. Le champ `commitment_anchored_on_chain` est forcé à `false`.

C’est-à-dire : existence vérifiable **sur le nœud qui a le journal**. Pas encore une hauteur `H` dans `blocks.jsonl`.

---

## 2. Fichiers

| Fichier | Rôle |
|---|---|
| `src/artcb/authz/registry.py` | Domain Manifest, Registry, export/import, vérif hash |
| `src/artcb/authz/genesis.py` | `import_org` / `import_group_genesis` après hash |
| `src/artcb/authz/domains.py` | `DOMAIN_MANIFEST` / `DOMAIN_BODY` dans la matrice |
| `src/artcb/authz/gate.py` | `DomainRegistry(data/authz/domains.json)` |
| `src/api/authz_routes.py` | `/domains`, `/locate`, `/body`, `/export`, `/import`, `/replicas` |
| `src/api/groups_routes.py` | manifeste GROUP à la création |
| `frontend/src/pages/Groups.tsx` | création ORG + mode de stockage + export/import |
| `tests/test_e2e218_domain_registry.py` | T-E45 |

---

## 3. Matrice protocole

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| Nœud héberge, fondateur possède | proposition 218 | audit collé | `registry.py` `node_owns_domain=false` | T-E45 | `ae5868f` ×4 ; ORG Alice `node_owns_domain=false` |
| Alice sans serveur crée une ORG | déjà 217 | | `POST /authz/orgs` + manifeste | T-E45 | live OVH1 `org_389303641163` / `domain_bd0289984a25` |
| Registry / routing local | proposition 218 | | `GET /authz/domains` `/locate` | T-E45 | OVH1 count=1 ; locate `hosted_here=true` |
| Export/import + hash | proposition 218 | | `export` / `import` | T-E45 | live export `200` `artcb_domain_export` |
| Réplica = intention, pas copie | proposition 218 | | `/replicas` `body_copied=false` | T-E45 | live hybrid liste `ovh-node-2` ; B n’a pas le domaine |
| Corps pas recopié sur les 4 nœuds | déjà 217 | | deux `TestClient` | T-E45 | **mesuré** : OVH2/AWS3/OVH4 `domains=0` |
| Ancrage `blocks.jsonl` | **non** | 217 P-217-2 | non | — | `commitment_anchored_on_chain=false` live |
| Chiffrement au repos | **non** | 217 P-217-1 | non | — | non |
| Signature autonome du fichier Genesis | **non** | 217 P-217-4 | session fondateur, pas Ed25519/ML-DSA du bundle | — | session live, pas objet autonome |

---

## 4. Ce qui reste (honnête)

- **P-218-1** (= P-217-1) Chiffrement au repos : le corps exporté/importé et `orgs.json` restent en clair sur le disque de l’hôte.
- **P-218-2** (= P-217-2) Le manifeste n’est pas un bloc public. Le registre n’est **pas** gossipé aux 4 nœuds. B ne « voit » l’ORG d’Alice que après import (ou si on ancre plus tard le hash).
- **P-218-3** (= P-217-3) Réplication automatique du corps entre nœuds autorisés : **non**. `/replicas` = liste. L’import est manuel / API.
- **P-218-4** (= P-217-4) L’export est autorisé par **session fondateur**, pas encore un objet signé Ed25519/ML-DSA autonome. Le nœud ne détient toujours pas la clé privée d’Alice.
- **P-218-5** Le journal de politiques n’est inclus dans l’export que s’il nomme l’ORG/GROUP. Les membres `data/groups/g_*.json` ne sont **pas** dans le bundle ORG. Un GROUP exporté n’emporte pas encore le fichier membres.
- **P-218-6** Mode `hybrid` enregistre `min_replicas=2` mais n’ouvre pas un 2ᵉ hôte tout seul.
- **P-218-7** Sur OVH1 live, `ARTCB_NODE_ID` n’est pas posé : `hosting_node_id` vaut l’identité P2P placeholder `artcb1_REMPLACER_PAR_VOTRE_ADRESSE`, pas `ovh-node-1`. Le fondateur n’est quand même **pas** ce nœud.

Je ne dis **pas** : « ARTCB a des shards privés distribués avec recovery automatique. »

Je dis : **le domaine a maintenant une identité (manifeste) distincte du serveur qui le stocke, Alice n’a pas besoin d’un nœud pour créer, et le fondateur peut extraire puis réinstaller le corps en revérifiant le hash. La réplication multi-nœuds, l’ancrage chaîne et le chiffrement au repos restent à faire.**

---

## 5. Live mesuré (2026-09-04, après `git push origin HEAD:main` + follow-main)

`origin/main` = `ae5868f33df3613ba6011ab7a11a4b54ffe80649`.  
Livre : `blocks.jsonl` **1 ligne** sur chaque nœud (pas de wipe). Certification **inchangée** (`true`).

| Nœud | IP | `/health.git_sha` | certified | `DOMAIN_MANIFEST` | `node_owns_domain` | `GET /authz/domains` | `POST /authz/orgs` anonyme | `GET /chain` anonyme | P2P privé |
|---|---|---|---|---|---|---|---|---|---|
| ovh-node-1 | 152.228.144.34 | `ae5868f` | true | oui | false | 1 (après Alice) | 401 | 1 bloc `public` | false |
| ovh-node-2 | 151.80.107.29 | `ae5868f` | true | oui | false | **0** | 401 | 1 bloc `public` | false |
| aws-node-3 | 51.44.222.232 | `ae5868f` | true | oui | false | **0** | 401 | 1 bloc `public` | false |
| ovh-node-4 | 91.134.45.8 | `ae5868f` | true | oui | false | **0** | 401 | 1 bloc `public` | false |

OVH1 HTTPS `:8443` = 200, même SHA.

### Parcours Alice réellement exécuté sur OVH1

1. Wallet de test `e2e218_alice` créé **sur le serveur** (le `POST /wallet/create` HTTP est bloqué par le fingerprint appareil — un seul wallet par device).
2. `POST /auth/login` → session.
3. `POST /authz/orgs` `{ name: Organisation Alice, storage_mode: hybrid }` → **200**.
4. Résultat mesuré :
   - `organization_id` = `org_389303641163`
   - `domain_id` = `domain_bd0289984a25`
   - `node_owns_domain` = **false**
   - `commitment_anchored_on_chain` = **false**
   - fondateur ≠ `hosting_node_id`
   - `GET /authz/domains/{id}/body` anonyme = **401**
   - `POST /authz/domains/{id}/export` session fondateur = **200** `artcb_domain_export`
   - projection publique OVH1 : hash + id, **pas** de `genesis_body`
5. Les 3 autres nœuds : `domains_count=0`, `orgs_count=0`, `commitments_count=0`. Ils **n’ont pas** `domain_bd0289984a25`.

C’est-à-dire : **créer l’organisation sur OVH1 ne copie ni le corps, ni le manifeste, ni même le hash, sur OVH2 / AWS3 / OVH4.** Le réseau global n’a pas encore un journal de commitments gossipé (P-218-2).

Script de mesure : `scripts/run_live218_domain_registry.py` (n’imprime aucun token).
