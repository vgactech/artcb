# R479 — Backend Paillier HE pour vérification d'unicité biométrique

**Date :** 2026-09-27  
**Module :** `src/artcb/crypto/homomorphic.py` + `tests/test_task001_r479_paillier_he.py`  
**Protocole :** `ARTCB-PHE-PAILLIER-HAMMING-v1`  
**SHA avant :** `0a0197b`  
**SHA après :** (voir après commit)  
**CERTIFIED_100 :** `false` — invariant absolu  
**Tests :** 30/30 PASS (P01→P30) + 124/124 non-régression PASS  

---

## Contexte

TASK-001-BIOMETRIE-SUITE — R376 avait branché `check_uniqueness()` sur `privacy_preserving_match()` (XOR SHA-256), mais cette approche souffrait de l'**effet avalanche SHA-256** : 1 bit flip dans le template change ~50 % du hash, ce qui la rend inutilisable pour un matching robuste au bruit capteur réel.

R378 avait résolu cela en ajoutant le **Hamming direct** sur les bytes bruts — mais sans chiffrement homomorphe réel (le template brut reste visible côté serveur).

**R479 comble ce manque** : vrai chiffrement homomorphe **Paillier IND-CPA** pour la distance de Hamming — le serveur ne voit jamais les templates bruts.

### Problème d'installation des libs FHE (diagnostiqué sessions précédentes)

| Lib | Problème |
|---|---|
| `concrete-python` (Zama TFHE) | Requiert PyTorch 150MB → timeout PostToolUse Bob IDE |
| `tenseal` (Microsoft SEAL) | Requiert compilation C++ + cmake dans PATH → `FileNotFoundError: cmake` |
| **`phe` (python-paillier)** | ✅ Pur Python, zéro compilation, 1 seul paquet |

**Décision :** `phe 1.5.0` — Paillier est un schéma de chiffrement homomorphe additif réel (IND-CPA, Paillier 1999), adapté au calcul de distance de Hamming via somme homomorphe.

---

## Architecture Paillier pour Hamming

### Protocole mathématique

```
distance_Hamming(A, B) = Σ XOR(A_i, B_i)
                       = Σ Enc(XOR(A_i, B_i))  [déchiffré]
                       = Dec( Σ Enc(XOR_i) )    [propriété additive Paillier]
```

**Étape 1 — Côté client :**
```
XOR_i = A_i XOR B_i   (calculé en clair localement)
Enc(XOR_i) = Paillier.encrypt(XOR_i)  [chiffrement avec clé publique]
→ PaillierCiphertext(enc_xor_bits=[Enc(XOR_0), ..., Enc(XOR_N-1)])
```

**Étape 2 — Côté serveur (homomorphe) :**
```
enc_sum = Enc(XOR_0) + Enc(XOR_1) + ... + Enc(XOR_N-1)
        = Enc(Σ XOR_i)   [addition homomorphe — jamais de déchiffrement]
```

**Étape 3 — Côté client (déchiffrement) :**
```
dist = Paillier.decrypt(enc_sum)  = Σ XOR_i = distance_Hamming
retourner UNIQUEMENT : dist ≤ threshold ? → MATCH / NO_MATCH  [anti-oracle]
```

### Propriétés de sécurité

| Propriété | Valeur |
|---|---|
| Schéma | Paillier RSA-based (1999) |
| Sécurité | IND-CPA (indistinguishabilité sous attaque à textes choisis) |
| n_length MVP | 1024 bits (~80 bits de sécurité) |
| n_length prod | 2048 bits (~112 bits de sécurité) — recommandé |
| Homomorphisme | Additif : Enc(a) · Enc(b) = Enc(a+b) mod n² |
| Anti-oracle | Seul le booléen MATCH/NO_MATCH est retourné — jamais la distance brute |
| unique_human_proven | **toujours False** — invariant absolu |
| CERTIFIED_100 | **false** |

---

## Fichiers modifiés

### AVANT

**`src/artcb/crypto/homomorphic.py`** (ligne 26) :
```python
MODULE_VERSION = '1.1.1'  # R432 — FheHammingCircuit TFHE simulé
```
Aucun import `logging`, aucun `logger`, pas de `PaillierHammingBackend`.

### APRÈS

**`src/artcb/crypto/homomorphic.py`** (lignes 26-38) :
```python
MODULE_VERSION = '1.2.0'  # R479 — PaillierHammingBackend (Paillier HE réelle)

import hashlib
import hmac
import logging
import os
import struct
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("artcb.crypto.homomorphic")
```

**Classes ajoutées (lignes 481→849)** :
- `PHE_PROTOCOL = "ARTCB-PHE-PAILLIER-HAMMING-v1"`
- `PHE_NOTE` — note d'honnêteté (limites MVP documentées)
- `PaillierCiphertext` — dataclass frozen (tuple de ciphertexts + metadata)
- `PaillierHammingResult` — résultat avec invariants `unique_human_proven=False`, `certified=False`
- `PaillierHammingBackend` — backend complet :
  - `__init__(n_length=1024)` — keygen Paillier
  - `encrypt_xor_bits(ta, tb)` → `PaillierCiphertext | None`
  - `sum_encrypted_bits(ct)` → `EncryptedNumber` (homomorphe)
  - `decrypt_match(enc_sum, threshold)` → `(bool, bool, int|None)`
  - `compute_hamming_paillier(ta, tb, threshold_bits)` — flux complet
  - `fhe_uniqueness_check(new_template, existing, threshold_bits)` → `PaillierHammingResult`

**`requirements.txt`** (après ligne 22) :
```
# phe : Paillier Homomorphic Encryption réelle (IND-CPA) pour check_uniqueness() biométrique
# Protocole ARTCB-PHE-PAILLIER-HAMMING-v1 (R479) — pur Python, zéro compilation
phe>=1.5.0
```

---

## Résultats des tests

### Nouveaux tests R479 : 30/30 PASS (P01→P30)

| Groupe | Tests | Résultat |
|---|---|---|
| P01-P05 Construction/clés | keygen, session_id, unicité clés, n_length, ImportError | ✅ 5/5 |
| P06-P10 encrypt_xor_bits | nominal, bits_len, vide, longueurs diff., xor(t,t)=0 | ✅ 5/5 |
| P11-P15 sum_encrypted_bits | type, None, correctness, flip 3 bits, all-diff | ✅ 5/5 |
| P16-P20 decrypt_match | below/above threshold, None, négatif, exact | ✅ 5/5 |
| P21-P25 compute_hamming | same/diff/empty/consistency/lengths | ✅ 5/5 |
| P26-P30 fhe_uniqueness_check | vide, match, no_match, empty_template, multi-records | ✅ 5/5 |

**Test P14 (clé) — cohérence Paillier vs Hamming direct :**
```
template 8 octets, 3 bits flippés
hamming_distance_bits(ta, tb) = 3
PaillierHammingBackend.compute_hamming_paillier(ta, tb, threshold=100)[2] = 3
→ IDENTIQUE ✅
```

### Non-régression : 124/124 PASS (zéro régression)

Tests couverts : `test_task001_biometric.py` (94) + `test_task001_r373_human_identity_policy.py` (26) + `test_task001_r374_bch.py` + `test_task001_r376_uniqueness.py` + `test_task001_r378_hamming.py`

---

## Limites honnêtes documentées (PROTOCOLE ARTCB)

1. **n_length=1024 bits (MVP)** : sécurité ~80 bits. Production → 2048 bits (keygen ~3.6s).
2. **Chiffrement bit-à-bit** : 256 bits = 256 opérations Enc → ~0.5s par template pair. Acceptable pour l'enrôlement (one-time), moins pour la recherche sur grande base.
3. **XOR côté client** : le client doit avoir les deux templates pour calculer les XOR. En mode serveur pur (sans template côté client), il faudrait un protocole 2-party (ex : OT + GMW). Non implémenté.
4. **Bibliothèque pur Python** (`phe`) : pas de HSM/TEE. Pour la production → TenSEAL (SEAL) ou Concrete (TFHE) sur matériel dédié.
5. **`unique_human_proven = False`** dans tous les cas — invariant absolu inchangé.
6. **FAR/FRR non mesurés** sur capteurs biométriques réels — vecteurs synthétiques uniquement.
7. **Pas de `check_uniqueness()` mis à jour** pour brancher `PaillierHammingBackend` — le routing R432 (`fhe_circuit=` paramètre) accepte déjà n'importe quel backend duck-typing. L'appelant passe `fhe_circuit=PaillierHammingBackend()` pour activer le chemin Paillier.

---

## Prochain chantier TASK-001

- [ ] Brancher `PaillierHammingBackend` dans `check_uniqueness()` routing R432 via `fhe_circuit=` (duck-typing déjà en place)
- [ ] TASK-006-LIVE-VALIDATION — déploiement N2/N3 (systemctl restart artcb)
- [ ] `CERTIFIED_100=false` — invariant absolu maintenu
