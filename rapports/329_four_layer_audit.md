# Rapport 329 — Audit 4 couches PUBLIC → ORG → GROUP → PRIVÉ (Issue #86)

**Date:** 2026-09-12T19:50:00Z  
**Commit:** `0e177b6c1aae4aadb5f535bb181a090243a0e226`  
**CERTIFIED_100:** `false`  
**Issue:** [#86](https://github.com/vgactech/artcb/issues/86)

## Verdict

R328 a fermé le **bug physique** (`height()` mixte → `not_extending`).  
R329 **n’invente pas** quatre ledgers dossiers : il **mesure le modèle réel du code** et ajoute des tests d’isolation + matrice de flux.

| Couche | Statut réel (code) | Tip public pollué ? |
|--------|--------------------|---------------------|
| PUBLIC | `visibility=public` + `chain/public/blocks.jsonl` + PBFT | — |
| ORG | Genesis body `authz/orgs.json` + commitment hash public | Non (body local) ; commitment **avance** le tip public **volontairement** |
| GROUP | `visibility=group` + `groups/*.json` + genesis authz | Non pour le tip public : écritures → **private book** (R328) |
| PRIVÉ | `visibility=private` + private book | Non |

## Vocabulaire (ne pas confondre)

1. **Visibilité chaîne HTTP** : `public | private | group` — **pas** `org`.
2. **Domaine logique** (`REPLICATION_MATRIX`) : global / org / group / resource / user.
3. `repo_scope` mappe `organization|group|private` → corps `append_block(visibility=private)` + hash public pour org.

Créer seulement `data/public` + `data/private` **ne certifie pas** ORG/GROUP.

## Matrice de flux (extraits CODE)

Artefact complet : `logs/R329/flow_matrix.json` (généré depuis `REPLICATION_MATRIX`).

| Objet | Couche | Réplication | Contenu public ? |
|-------|--------|-------------|------------------|
| GLOBAL_GENESIS | global | all_consensus_nodes | règles protocole |
| ORG_GENESIS_HASH | global | all_consensus_nodes | kind+id+hash seulement |
| ORG_GENESIS_BODY | org | org_domain_nodes | Non (P2P) |
| GROUP_GENESIS_HASH | global | all_consensus_nodes | hash + parent |
| GROUP_MEMBERS | group | group_domain_nodes | Non |
| PRIVATE_RESOURCE | resource | never_p2p | Non |
| DOMAIN_COMMITMENT_BLOCK | global | all_consensus_nodes | bloc public reward=0 |

## Tests ajoutés

`tests/test_r329_four_layer_isolation.py` (6 PASS) :

- croissance private+group → `public_last_index` inchangé
- ORG-A / ORG-B + même nom de groupe → IDs distincts ; B ne write pas dans groupe A
- commitment org = projection publique sans `founder_address`
- restart `ChainManager` conserve tip public malgré suffixe privé
- write_certified public après 200 blocs « org-like » privés

## Gaps honnêtes (OPEN)

| Gap | Détail |
|-----|--------|
| ACL ORG implicite | Pas de READ chaîne par `organization_id` seul (sidecar ResourceIndex) |
| 3ᵉ ledger GROUP | Non : group → private book R328 |
| Auto VIEW-CHANGE E–H | Toujours **NOT_PROVEN** live |
| Restart nœud live | SSH :22 timeout → **NOT_PROVEN** (restart unitaire PASS) |
| Issue #86 corps GitHub | Au fetch API, texte encore R328 A–F ; extension 4 couches reçue ici / chat |

## Live

Voir `logs/R329/measurement.json`. Tip public ×4 + `ledger_mode=split_v1` attendus ; **four_layer_certified=false**.

## Suite (pas une clôture)

1. Auto VC mesuré (timeout → NEW-VIEW → Q)  
2. Restart process live ×1 seed  
3. Optionnel : ACL multi-tenant ORG explicite (si protocole l’exige)  
4. Ne pas déclarer `CERTIFIED_100` tant que 4 couches + E–H + J live ne sont pas fermés
