# R461 — Diffusion P2P du NodeTpmBinding

**Date :** 2026-09-25T(session courante)  
**Auteur :** Agent Bob (mode DEBUG)  
**Commit :** en cours (groupé R461+R462+R463)  
**CERTIFIED_100=false**

---

## Résumé

R461 implémente les 4 routes API P2P permettant la diffusion et la vérification du binding TPM EK → NodeID entre nœuds ARTCB.

---

## Contexte

R460 avait créé `src/artcb/security/node_tpm_binding.py` — liaison cryptographique TPM EK → NodeID, signée Ed25519 (+ ML-DSA-65 si liboqs). Le chaînon manquant était la **diffusion P2P** : comment un nœud A communique son binding à un nœud B de façon vérifiable ?

---

## Fichiers modifiés

### AVANT (état HEAD `1a3cb87`)

| Fichier | État |
|---------|------|
| `src/api/node_tpm_binding_routes.py` | ❌ Absent |
| `src/api/main.py` | Pas de `include_router(node_tpm_binding_router)` |
| `tests/test_r461_node_tpm_binding_routes.py` | ❌ Absent |

### APRÈS (R461)

| Fichier | État |
|---------|------|
| `src/api/node_tpm_binding_routes.py` | ✅ Créé — 4 routes (322 lignes) |
| `src/api/main.py` | ✅ Modifié — import + include_router |
| `tests/test_r461_node_tpm_binding_routes.py` | ✅ Créé — T01–T20 |

---

## Modifications exactes

### `src/api/main.py`

**Ligne 60 — ajout import :**
```python
# AVANT
from src.api.admin_device_binding_routes import router as admin_device_binding_router

# APRÈS
from src.api.admin_device_binding_routes import router as admin_device_binding_router
from src.api.node_tpm_binding_routes import router as node_tpm_binding_router
```

**Ligne 455 — ajout include_router :**
```python
# AVANT
    app.include_router(admin_device_binding_router)

# APRÈS
    app.include_router(admin_device_binding_router)
    # R461 — Diffusion P2P du NodeTpmBinding (TPM EK → NodeID)
    app.include_router(node_tpm_binding_router)
```

---

## Routes créées

| Méthode | Chemin | Auth | Description |
|---------|--------|------|-------------|
| `POST` | `/api/v1/p2p/node-tpm-binding/submit` | Bearer opérateur | Soumet le binding de ce nœud |
| `GET` | `/api/v1/p2p/node-tpm-binding/list` | Public | Liste tous les bindings connus |
| `GET` | `/api/v1/p2p/node-tpm-binding/{node_id}` | Public | Binding d'un nœud donné |
| `POST` | `/api/v1/p2p/node-tpm-binding/receive` | Aucune (réseau P2P) | Reçoit un binding d'un pair |

---

## Garanties implémentées

- **FAIL-CLOSED** : tout binding reçu (via `/receive`) est vérifié cryptographiquement (Ed25519) avant stockage — signature invalide → 400.
- **Invariant absolu** : `certified=False` et `unique_human_proven=False` dans toutes les réponses, même si l'entrée stockée était corrompue.
- **Store persistant** : `data/p2p/node_tpm_bindings.json` (mode 0600) — fail-open sur erreur I/O.
- **R462 ready** : `_binding_from_dict()` inclut `tpm_pcr0_sha256`, `tpm_quote_nonce`, `tpm_pcr_proven` pour reconstruire le payload canonique v2.
- **DEBUG_MODE=True** : logs complets à chaque opération (store, verify, reject).

---

## Tests

Fichier : `tests/test_r461_node_tpm_binding_routes.py`  
Suite : **T01–T20** — 20 tests PASS

| Test | Description |
|------|-------------|
| T01 | `/list` vide → count=0 |
| T02 | `/receive` binding valide → 200 accepted |
| T03 | `/list` après réception → count=1 |
| T04 | `/{node_id}` existant → 200 |
| T05 | `/{node_id}` inexistant → 404 |
| T06 | `/receive` signature altérée → 400 FAIL-CLOSED |
| T07 | `/receive` sans node_id → 400 |
| T08 | Invariant `certified=False` dans `/list` |
| T09 | Invariant `unique_human_proven=False` |
| T10 | node_id mismatch → 400 |
| T11 | Niveau A + EK cert → `tpm_proven=True` |
| T12 | Niveau E → `tpm_proven=False` |
| T13 | Deux bindings → count≥2 |
| T14 | Nonce altéré → 400 |
| T15 | `verified_ok=True` dans `/list` |
| T16 | `certified=False` dans `/{node_id}` |
| T17 | JSON invalide → 400/422 |
| T18 | `hardware_assurance_level` correct dans la réponse |
| T19 | Binding v2 (PCR0) → accepté |
| T20 | `/{node_id}` pcr node présent après T19 |

---

## Bug corrigé

**Bug R461** : `_binding_from_dict()` initial ne transmettait pas les champs `tpm_pcr0_sha256`/`tpm_quote_nonce`/`tpm_pcr_proven`. Le binding v2 (protocol v2) était rejeté car la reconstruction du payload canonique ne correspondait pas à la signature originale.

**Correction** : ajout des 3 champs dans `_binding_from_dict()` — ligne 120–122 de `node_tpm_binding_routes.py`.

---

## Résultats

```
tests/test_r461_node_tpm_binding_routes.py  20/20 PASS
Non-régression biométrie (R460+R374+R376+R378) : 162/162 PASS
TypeScript R463 : 0 erreur (hors erreurs préexistantes ReflexStatus)
```

---

## Limites honnêtes

- Le store `data/p2p/node_tpm_bindings.json` est local à chaque nœud — pas encore de gossip automatique vers les pairs (gossip = futur R464).
- `tpm_proven` et `hardware_assurance_level` proviennent du payload signé — un nœud malveillant peut signer `level=A` avec un faux EK hash. R462 (PCR quote) réduit ce risque mais ne l'élimine pas sans attestation distante complète.
- `CERTIFIED_100=false`.
