# R378 — Matching Hamming direct sur template_bytes

**Date :** 2026-09-18  
**Commit :** (pending)  
**Statut :** ✅ DONE — 28/28 tests PASS — non-régression 164/164  
**CERTIFIED_100 :** false  

---

## 1. Objectif

Résoudre la limite fondamentale de R376 : le XOR SHA-256 est détruit par l'**effet avalanche** des fonctions de hachage cryptographiques. 1 bit flip dans le template → ~50% des bits du hash changent → matching impossible.

R378 opère directement sur les `template_bytes` bruts, sans hachage intermédiaire.

---

## 2. Problème de R376 (rappel)

```
R376 — XOR sur SHA-256

template A ──SHA-256──→ hash_A
template B ──SHA-256──→ hash_B     (B = A + 1 bit flip)
XOR(hash_A, hash_B) ≈ 128 bits différents  ← MAUVAIS
```

L'effet avalanche de SHA-256 fait que deux templates très proches produisent des hashs très différents. La distance XOR sur les hashs ne mesure **pas** la proximité biométrique.

---

## 3. Solution R378 — Distance de Hamming directe

```
R378 — Hamming direct

template A
template B = A + 1 bit flip
hamming_distance_bits(A, B) = 1 bit  ← CORRECT
```

### Fonctions ajoutées

| Fonction | Rôle |
|----------|------|
| [`hamming_distance_bits(a, b)`](src/artcb/identity/biometric_onchain.py) | Compte les bits différents entre deux byte-strings |
| [`hamming_similarity(a, b)`](src/artcb/identity/biometric_onchain.py) | Similarité normalisée [0,1] = 1 - dist/max_bits |
| [`HammingMatchResult`](src/artcb/identity/biometric_onchain.py) | Dataclass résultat avec `hamming_distance`, `hamming_similarity`, `threshold_bits` |
| [`hamming_uniqueness_check()`](src/artcb/identity/biometric_onchain.py) | Vérification d'unicité via Hamming — remplace XOR SHA-256 |

### Interface `hamming_uniqueness_check()`

```python
hamming_uniqueness_check(
    new_template_bytes: bytes,
    existing_records: list[dict],
    *,
    threshold_bits: int | None = None,    # seuil absolu (bits)
    threshold_ratio: float | None = None, # seuil relatif [0,1]
) -> HammingMatchResult
```

Records : clé `template_bytes_b64` (base64) ou `template_bytes_hex` (hex).  
Les records sans template_bytes sont ignorés silencieusement (compatibilité ascendante).

---

## 4. Matrice FAR/FRR simulée (T27)

Template 32 octets (256 bits), `threshold_bits=8` :

| Distance (bits) | Match | Verdict |
|-----------------|-------|---------|
| 0 | ✅ True | TP (intra, bruit ≤ seuil) |
| 1 | ✅ True | TP (intra, bruit ≤ seuil) |
| 2 | ✅ True | TP (intra, bruit ≤ seuil) |
| 4 | ✅ True | TP (intra, bruit ≤ seuil) |
| 8 | ✅ True | TP (intra, bruit ≤ seuil) |
| **9** | ❌ False | TN (intra, bruit > seuil) |
| 16 | ❌ False | TN |
| 32 | ❌ False | TN |
| 64 | ❌ False | TN |
| 128 | ❌ False | TN |
| 200 | ❌ False | TN |
| 256 | ❌ False | TN |

Seuil exact et prévisible : dist ≤ threshold → match, dist > threshold → no-match.

---

## 5. Séparation intra/inter-classe simulée (T28)

| Comparaison | Distance | Match | Verdict |
|-------------|----------|-------|---------|
| Alice intra (capture 1, bruit 2 bits) | 2 bits | ✅ True | Bon |
| Alice intra (capture 2, bruit 6 bits) | 6 bits | ✅ True | Bon |
| Bob inter-classe | 117 bits | ❌ False | Bon |

**Ratio de séparation : 117 / 6 = 19.5×** — excellente séparation sur vecteurs synthétiques.

---

## 6. Avant / Après

### Avant R378 (R376 — XOR SHA-256)

```python
# homomorphic.py — privacy_preserving_match()
ha = bytes.fromhex(commitment_a.template_hash_hex)
hb = bytes.fromhex(commitment_b.template_hash_hex)
xor_dist = sum(bin(b).count("1") for b in _xor_bytes(ha, hb))
similarity = 1.0 - (xor_dist / max_bits)  # EFFET AVALANCHE
```

1 bit flip dans le template → ~128/256 bits différents dans le hash → similarity ≈ 0.5 → no-match incorrect.

### Après R378 (Hamming direct)

```python
# biometric_onchain.py — hamming_distance_bits()
return sum(bin(x ^ y).count("1") for x, y in zip(a_padded, b_padded))
```

1 bit flip dans le template → 1 bit différent → distance = 1 → match si threshold ≥ 1.

---

## 7. Seuil par défaut

`hamming_uniqueness_check()` avec seuil par défaut = **5% de max_bits** :
- Template 32 octets (256 bits) → seuil = 12 bits
- Template 64 octets (512 bits) → seuil = 25 bits

**⚠️ Ce seuil est arbitraire et non calibré sur capteurs réels.**  
Il DOIT être ajusté via mesure FAR/FRR sur population réelle avant tout usage production.

Le seuil BCH `t=8 bits/bloc` de R374 est une référence cohérente pour les tests.

---

## 8. Honnêteté — Limites R378

| Limite | Détail |
|--------|--------|
| Vecteurs synthétiques | La séparation intra/inter repose sur SHA-256(seed) ≠ vrais capteurs |
| Dépendance au pipeline | La distance Hamming n'est pertinente que si les templates sont normalisés identiquement (même capteur, même orientation, même extraction) |
| FAR/FRR non mesurés | Aucune mesure sur NIST BSSR ou équivalent |
| `unique_human_proven=False` | Invariant absolu — pas de preuve d'identité humaine |
| `CERTIFIED_100=false` | Invariant absolu |
| SHA-256 XOR (R376) non remplacé | R378 est une NOUVELLE méthode additionnelle (`hamming_direct`) — R376 est conservé |

---

## 9. Tests — 28/28 PASS

| Tests | Couverture |
|-------|-----------|
| T01–T08 | Primitives `hamming_distance_bits()` + `hamming_similarity()` |
| T09–T14 | `hamming_uniqueness_check()` — match/no-match selon seuil |
| T15–T19 | Invariants absolus |
| T20 | Records sans template_bytes ignorés |
| T21–T26 | Champs du résultat `HammingMatchResult` |
| T27 | **Matrice FAR/FRR simulée** — 12 points de distance |
| T28 | **Séparation intra/inter-classe simulée** — ratio 19.5× |

---

## 10. Non-régression — 164/164 PASS

| Suite | Avant R378 | Après R378 |
|-------|-----------|-----------|
| test_task001_biometric.py | 18 | 18 |
| test_task001_r374_bch.py | 30 | 30 |
| test_task001_r373_human_identity_policy.py | 26 | 26 |
| test_add_device_r363.py | 20 | 20 |
| test_r375_rule_corpus_telemetry.py | 20 | 20 |
| test_task001_r376_uniqueness.py | 22 | 22 |
| **test_task001_r378_hamming.py** | — | **28** |
| **TOTAL** | **136** | **164** |

---

## 11. Prochaine étape

| Décision à prendre | Description |
|--------------------|-------------|
| Calibrage seuil sur capteurs réels | Mesurer FAR/FRR sur base NIST BSSR ou équivalent |
| Pipeline de normalisation | Définir comment le template biométrique est normalisé avant stockage |
| FHE si nécessaire | Si la distance Hamming directe est suffisante → FHE SEAL/OpenFHE non nécessaire |

---

*CERTIFIED_100=false | unique_human_proven=False — invariant absolu*
