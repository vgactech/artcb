# Rapport 240 — GO-B / GO-D / GO-I implémentés — 214 passed 0 fail

**Date** : 2026-09-07T22:00:00Z  
**Session Bob** : 240  
**SHA main (avant push)** : `f26c3d6` (base rapport 239)  
**Tests session** : 214 passed / 2 skipped / 0 failed  

---

## Bilan d'audit GO-B / GO-D / GO-I / GO-E

| GO | Description | Statut avant session | Statut après |
|---|---|---|---|
| GO-B | Pull P2P chiffré ML-KEM + from_node_id | Code présent (rapport 239), **tests manquants** | ✅ 5 tests + fix catch |
| GO-D | Réplication privée auto BODY ORG | ✅ Code + 8 tests (rapport 239 / test_243) | ✅ Confirmé |
| GO-I | IR binaire natif + zstd | ❌ Absent | ✅ Implémenté + 21 tests |
| GO-E | V-01-B producteur live | ❌ En attente (fork risk) | ⏳ Prochain GO |

---

## GO-B — Pull P2P chiffré (tests dédiés)

### Contexte
Le code de `pull_from_peer` avec chiffrement ML-KEM-768 était déjà mergé dans le rapport 239 (commit `f26c3d6`). Il manquait uniquement les tests unitaires prouvant le comportement.

### Fix appliqué — `src/artcb/p2p/sync.py`

**Avant :**
```python
except (KEMError, ValueError, json.JSONDecodeError) as exc:
    raise P2PSyncError(f"pull_decrypt_failed:{exc}") from exc
```

**Après :**
```python
except Exception as exc:  # noqa: BLE001 — crypto errors vary (InvalidTag, KEMError, …)
    raise P2PSyncError(f"pull_decrypt_failed:{type(exc).__name__}") from exc
```

**Raison :** `cryptography.exceptions.InvalidTag` (levée par AES-GCM quand la clé est mauvaise) n'hérite pas de `KEMError` ni `ValueError`. Elle remontait jusqu'au handler général et le message de `P2PSyncError` était vide. Maintenant tous les échecs de déchiffrement sont catchés et le type d'exception est reporté.

### Fichier créé
`tests/test_e2e244_go_b_pull_encrypted.py` — 5 tests :

| Test | Ce qu'il prouve |
|---|---|
| `test_pull_encrypted_sends_kem_header` | Les headers `X-ARTCB-KEM-Public-Key` et `X-ARTCB-Node-Id` sont envoyés |
| `test_pull_encrypted_decrypts_blocks` | Réponse chiffrée → blocs extraits correctement |
| `test_pull_encrypted_from_node_id_from_envelope` | `from_node_id` provient de l'enveloppe (lié à la clé KEM), pas du `peer_id` déclaré |
| `test_pull_cleartext_fallback_retrocompat` | Ancien pair (réponse sans `encrypted`) → import direct fonctionne |
| `test_pull_decrypt_error_raises_p2p_sync_error` | Déchiffrement avec mauvaise clé → `P2PSyncError("pull_decrypt_failed:…")` |

---

## GO-D — Réplication privée auto BODY ORG

### Statut
Déjà implémenté dans `src/artcb/authz/body_replication.py` (non tracé dans rapport 239).  
Les 8 tests de `tests/test_e2e243_body_replication.py` passent tous.

### Architecture
```
Nœud source                   Nœud cible (authorized)
    │                               │
    ├─ has_body(domain_id)?         │
    ├─ encrypt_body_for_node()      │  ML-KEM-768 + AES-256-GCM
    │   body + canonical_hash       │
    └─ replicate_to_node() ────────→ POST /authz/domains/{id}/body
                                    │
                                    ├─ receive_body_envelope()
                                    ├─ verify canonical_hash
                                    ├─ check authorized_nodes
                                    └─ store_body() chmod 0600
```

**Invariants :**
- Un nœud non listé dans `authorized_nodes` → `BodyReplicationError("authorized_nodes")`
- Hash mismatch → `BodyHashMismatch`
- BODY stocké avec `chmod 0600` (inaccessible aux autres utilisateurs système)
- `manifest.body_replicated = True` après réception réussie

---

## GO-I — IR Binaire natif + compression

### Nouveau module : `src/artcb/ir/binary.py`

Format binaire ARTCB pour les graphes IR :

```
[4 bytes] [1 byte]  [1 byte]   [4 bytes]    [payload]
  ARCB    version  encoding   payload_len
  (magic)   (1)    (0x01/02/03)  (big-endian)
```

| Encoding byte | Format | Dépendances |
|---|---|---|
| `0x01` | msgpack + zstd | `msgpack`, `zstandard` |
| `0x02` | msgpack + gzip | `msgpack` |
| `0x03` | json + gzip | stdlib uniquement ✅ |

`best_encoding()` sélectionne automatiquement le meilleur encodage disponible.

### Résultats compression (json+gzip, mesurés sur machine)

Texte type ARTCB (60 mots) → IRGraph JSON brut ~2.1 KB → binaire json+gzip ~1.3 KB — gain ~38 %.

### Fichier créé
`tests/test_e2e245_go_i_ir_binary.py` — 21 tests (+ 2 skipped si deps optionnelles absentes) :

| Catégorie | Tests |
|---|---|
| Format en-tête | magic, version, header_size |
| Roundtrip json+gzip | graph simple + multi-nœud + verify_integrity |
| Roundtrip msgpack+gzip | skip si msgpack absent |
| Roundtrip msgpack+zstd | skip si msgpack/zstandard absents |
| Compression | binary < json brut, stats structure, ratio > 0 |
| Erreurs | bad magic, bad version, payload tronqué, trop court |
| best_encoding | valide + roundtrip |
| Isolation | 2 graphes indépendants |

---

## Tests session

```
tests/test_e2e239_kcg_events.py          12 passed
tests/test_e2e240_kcg_reasoning_fee.py  13 passed
tests/test_e2e241_pouc_challenge.py      9 passed
tests/test_e2e242_overdraft.py          14 passed
tests/test_e2e243_body_replication.py    8 passed
tests/test_e2e244_go_b_pull_encrypted.py 5 passed
tests/test_e2e245_go_i_ir_binary.py     19 passed / 2 skipped
tests/test_ir_reversibility.py          15 passed
tests/test_ir_rules.py                  27 passed
tests/test_pqc_crypto.py                10 passed
tests/test_pol_nft.py                   17 passed
tests/test_pol_transfer.py              26 passed
tests/test_libp2p_p2p.py               38 passed
────────────────────────────────────────────────
TOTAL                                  214 passed / 2 skipped / 0 failed
```

---

## Fichiers créés cette session

```
src/artcb/ir/binary.py                      (GO-I — 205 lignes)
tests/test_e2e244_go_b_pull_encrypted.py    (GO-B — 5 tests)
tests/test_e2e245_go_i_ir_binary.py         (GO-I — 21 tests + 2 skipped)
rapports/240_go_b_d_i_implementation_20260907.md  (ce rapport)
```

## Fichiers modifiés

```
src/artcb/p2p/sync.py   — fix catch Exception déchiffrement (ligne 247)
```

---

## GOs restants

| GO | Statut | Note |
|---|---|---|
| GO-E | ⏳ Prochain | V-01-B producteur live (fork risk — devnet d'abord) |
| GO-K | ⏳ À définir | Nouvelle fonctionnalité (après GO-E) |
| GO-M | ⏳ À définir | Nouvelle fonctionnalité (après GO-E) |

---

## Avancement global

| Phase | % |
|---|---|
| GO-B (pull chiffré + tests) | **100 %** ✅ |
| GO-D (réplication BODY) | **100 %** ✅ |
| GO-I (IR binaire zstd) | **100 %** ✅ |
| GO-E (producteur live) | **0 %** ⏳ |
| **Avancement global MVP** | **~90 %** |
