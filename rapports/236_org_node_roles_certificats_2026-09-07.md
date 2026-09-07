# Rapport 236 — HOST ≠ REPLICA ≠ CONSENSUS (7 septembre 2026)

**Source :** audit GitHub du `main` actuel + GO d’exécuter correctement la distinction Genesis ORG.  
**SHA `main` / live au départ :** `75eb97d2aa053a084696614adc769d65dd170b0f`  
**Suite 235 :** 857 passed / **9 skipped** / 0 failed. Ce n’est **pas** « 857 exécutés / 0 anomalie ».  
**Aucune D-0xx.** Certification **non retouchée**. Tip public **non touché**.  
**Ce n’est pas** une blockchain privée ORG certifiée, ni V-01-B producteur, ni PoUC.

---

## 1. Réponse directe — Genesis d’une ORG

Le modèle **déjà codé** (217–218) est correct, avec la nuance que tu viens de figer :

```text
blockchain publique ARTCB
        │
        │ DOMAIN_COMMITMENT  (hash seulement)
        ▼
ORG ACME — fondateur Alice (humain)
        │
        ├── Node Paris     héberge le BODY
        └── Node Frankfurt déclaré dans authorized_nodes
                           BODY pas encore copié
```

| Élément | Partagé | Qui |
|---|---|---|
| Genesis global ARTCB | complet | nœuds de consensus |
| Manifest ORG | id + hash + hôtes | projection publique |
| Genesis ORG BODY | constitution | hôtes autorisés, **pas auto** |
| Membres / docs | privé | jamais P2P public |
| Commitment | hash | chaîne publique |

`founder_address ≠ hosting_node_id`. `node_owns_domain = false`.  
OVH1 qui disparaît **n’emporte pas** la propriété d’ACME.

---

## 2. La règle oubliée du CDC — maintenant du rang 3

**Avant :** `authorized_nodes += node-frankfurt` ressemblait à une autorisation forte.

**Après 236 :**

```text
déclaré (liste JSON)     ≠     certifié (signature fondateur)
HOST_ONLY                ≠     REPLICA              ≠     CONSENSUS
nœud                     ≠     membre humain        ≠     propriétaire machine
```

| Rôle nœud | HOST | REPLICATE | PRODUCE | VALIDATE | CHANGE_GOVERNANCE | TRANSFER_OWNERSHIP |
|---|---|---|---|---|---|---|
| HOST_ONLY | oui | non | non | non | non | **jamais** (humain) |
| REPLICA | oui | oui | non | non | non | non |
| CONSENSUS | oui | oui | oui | oui | non | non |
| GOVERNANCE | oui | oui | oui | oui | oui | non |

C’est-à-dire : un hébergeur Frankfurt peut être **HOST_ONLY** sans jamais produire un bloc ORG ni vendre ACME.

`add_replica` reste **intent** : `body_copied=false`. Le BODY arrive toujours par export/import + `canonical_hash`.

Un certificat contient :

```text
domain_id + node_id + node_public_key + role + genesis_hash
+ founder_address + founder Ed25519 signature
```

Le nœud doit ensuite **prouver** la clé privée correspondant à `node_public_key`. Sans les deux : `can_produce=false`, même si le nom est dans la liste.

---

## 3. Ce qui est démontré / ce qui ne l’est pas

| Élément | État | Preuve |
|---|---|---|
| ORG Genesis ≠ Global Genesis | **OK** | 217–218 + live |
| Fondateur ≠ machine | **OK** | T-E45 `node_owns_domain=false` |
| `authorized_nodes` | **OK déclaration** | T-E45 / T-E50 |
| export/import + hash | **OK** | T-E45 falsification `ACME`→`HACKED` refusée |
| Certificat nœud signé | **OK local** | T-E50 |
| Liste ≠ preuve | **OK local** | T-E50 CONSENSUS déclaré → `can_produce=false` |
| Réplication privée automatique | **NON** | P-218-3 / P-217-3 |
| Consensus privé ORG | **NON** | pas de BFT ORG |
| Producteur ORG de secours | **NON** | V-01-B producteur toujours rouge |
| 5 nœuds convergents (234) | **mesuré** sur SHA `1c2b873` | ≠ failover producteur |
| 857/0 fail | **suite verte** | 9 skipped à garder |
| PoUC / KCG | **non codé** | rang 6 |

---

## 4. Matrice protocole

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| Hôte ≠ propriétaire | 218 | 219 | `node_owns_domain=false` | T-E45 | OVH1 héberge, Alice possède |
| Replica ≠ copie BODY | 218 | audit | `add_replica` | T-E45 / T-E50 | — |
| HOST ≠ CONSENSUS | audit 236 | ce rapport | `node_roles.py` | T-E50 | non |
| Certificat nœud | audit 236 | ce rapport | `node_cert.py` | T-E50 | non |
| Auto-réplication ORG | non | — | non | non | non |
| V-01-B producteur | GO reçu, **pas exécuté ici** | 225 | — | — | non |

V-01-B producteur reste un **essai live de fork**. Je ne l’ai pas lancé dans ce commit : ce verrou est distinct de la constitution ORG.

---

## 5. Fichiers

- `src/artcb/authz/node_roles.py`
- `src/artcb/authz/node_cert.py`
- `src/artcb/authz/registry.py` (`declared_node_roles`, `node_certificates`)
- `POST /api/v1/authz/domains/{id}/node-certificates`
- `GET /api/v1/authz/domains/{id}/nodes/{node_id}`
- `tests/test_e2e236_org_node_roles.py` (T-E50)

Contact : `official@artcb.space`.
