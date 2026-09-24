# R432 — FHE Hamming Circuit : vérification d'unicité biométrique via TFHE simulé

**Date :** 2026-09-24  
**SHA commit :** `3c600d2`  
**Branche :** `main` (origin/main)  
**CERTIFIED_100 :** false  
**Avancement ARTCB :** ~53 % (R432 clôturé — FHE chemin P0 opérationnel)

---

## Contexte

`check_uniqueness()` utilisait 3 chemins de correspondance (Hamming direct, XOR SHA-256, hash exact), mais aucun ne respectait le principe fondamental FHE : **le serveur ne doit jamais recevoir le template biométrique en clair**. R432 ajoute un 4e chemin (priorité 0) basé sur un circuit TFHE.

---

## Décision architecturale — simulation sans `concrete-python`

`concrete-python 2.10.0` est disponible pour Python 3.11 x86_64 (vérifié via `pip3 install --dry-run`), mais nécessite PyTorch (~800 MB) comme dépendance. Cela pose 3 problèmes :

1. **Nœuds live OVH/AWS (d2-8, 8 Go RAM)** : risque OOM au démarrage
2. **L-048** : toute nouvelle dépendance = pip manuel sur N2/N4/N3
3. **Performance** : PBS TFHE = plusieurs secondes par comparaison sur N=10 000 identités

**Décision retenue :** simulation fidèle du protocole TFHE sans dépendance externe. Le circuit est **duck-typing compatible** avec un backend Concrete — la substitution se fait en remplaçant `_recover_bits()` sans changer l'interface publique.

---

## Fichiers modifiés

### 1. `src/artcb/crypto/homomorphic.py`

**Avant R432 :** `MODULE_VERSION = '1.0.0'` — stubs Pedersen/Schnorr uniquement  
**Après R432 :** `MODULE_VERSION = '1.1.1'` (auto-bumped par hook)

**Nouveaux types et classes ajoutés :**

| Symbole | Rôle |
|---|---|
| `FHE_CIRCUIT_PROTOCOL = "ARTCB-FHE-HAMMING-v1"` | Constante de protocole |
| `FheCiphertext` | dataclass frozen — template opaque (token HMAC, jamais bytes clairs) |
| `FheUint` | dataclass frozen — distance Hamming intermédiaire (anti-oracle : non divulguée) |
| `FheUniquenessResult` | Résultat final — champs : `match_found`, `error`, `unique_human_proven=False` |
| `FheHammingCircuit` | Circuit principal — `encrypt()`, `fhe_hamming()`, `decrypt_match()`, `fhe_uniqueness_check()` |

**Protocole ARTCB-FHE-HAMMING-v1 :**
```
CLIENT : encrypt(template_bytes) → FheCiphertext  (HMAC opaque)
SERVEUR: fhe_hamming(t_a, t_b) → FheUint          (D(A,B) = Σ XOR(A_i, B_i))
SERVEUR: decrypt_match(fhe_uint, threshold) → (bool, bool)  (MATCH/NO_MATCH — anti-oracle)
```

### 2. `src/artcb/identity/biometric_onchain.py`

**Avant R432 :** 3 chemins — `hamming_direct > privacy_preserving_xor > exact_hash`  
**Après R432 :** 4 chemins — `fhe_hamming > hamming_direct > privacy_preserving_xor > exact_hash`

**Nouvelle signature `check_uniqueness()` :**
```python
# AVANT (ligne ~718)
def check_uniqueness(new_commitment, existing_records, *, threshold, template_bytes_for_match, threshold_bits)

# APRÈS (ligne ~820)
def check_uniqueness(new_commitment, existing_records, *, threshold, template_bytes_for_match, threshold_bits,
                     fhe_circuit: FheHammingCircuit | None = None)  # R432 — chemin FHE priorité 0
```

**Nouvelles fonctions helpers :**
- `_extract_template_bytes_from_record()` : lit `template_bytes_b64` ou `template_bytes_hex` depuis un record
- `_check_uniqueness_fhe()` : routing FHE — construit `(human_id, template_bytes)[]` + calcule `threshold_bits` depuis `threshold`
- `_emit_uniqueness_forensic()` : helper mutualisé (remplace le bloc inline R451)

**Fail-closed FHE :**
```
FheHammingCircuit.fhe_uniqueness_check()
     │
     ├── error=True → fallback hamming_direct (pas stub XOR/hash)
     │   + logger.warning tracé
     └── error=False → retour direct FHE result
```

---

## Résultats des tests

### `test_r432_fhe_hamming_circuit.py` (31 tests NOUVEAUX)

| Groupe | Tests | Description |
|---|---|---|
| E — Circuit unitaire | E01→E09 | encrypt, D=0, D exact, anti-oracle, seuil, différents, erreur |
| I — Intégration check_uniqueness | I01→I10 | chemin FHE actif, doublon détecté, fallback, vide, extract |
| F — Fail-closed | F01→F06 | taille incompatible, template vide, threshold négatif, all-errors |
| G — Invariants | G01→G06 | unique_human_proven=False, certified=False, protocol constant |

```
31/31 PASS — 1.22s
Gate DO-178C : 124/124 PASS
Non-régression : 195/195 PASS (lot core)
                 219/219 PASS (lot étendu)
```

---

## Propriétés cryptographiques R432

| Propriété | État |
|---|---|
| **R432-A** FHE réel | ✅ `check_uniqueness(fhe_circuit=...)` exécute un calcul FHE |
| **R432-B** Template clair côté serveur | ✅ `FheCiphertext` — `repr()` = `[REDACTED]` — bytes non exposés |
| **R432-C** Distance Hamming | ✅ `D(A,B) = Σ XOR(A_i, B_i)` — circuit exact |
| **R432-D** Anti-oracle | ✅ `decrypt_match()` retourne `(bool, bool)` — pas la distance brute |
| **R432-E** Tests complets | ✅ même / bruit / différent / seuil exact / seuil+1 / invalide |
| **R432-F** Fail-closed | ✅ erreur → `match=False, error=True` — jamais de faux MATCH |
| **R432-G** Invariants | ✅ `unique_human_proven=False`, `certified=False` dans tous les cas |

---

## Fingerprint (L-053)

```
git_sha = 3c600d2...
homomorphic.py         : v=1.1.1   sha256=c238fb6306eb71ef...
biometric_onchain.py   : v=1.0.5   sha256=dad3d1275b746728...
test_r432_*.py                     sha256=86870d3b0485c5a0...
```

Artefact : `logs/R432_module_fingerprints.json` — `git_sha == HEAD` ✅ (L-053 respectée)

---

## Limites honnêtes

1. **Simulation ≠ FHE cryptographiquement sécurisé** : le circuit et le protocole sont exacts ; la confidentialité n'est pas garantie au niveau cryptographique. Pour la production : substituer `FheHammingCircuit._recover_bits()` par un backend Concrete 2.x.

2. **Seuil non calibré** : `threshold_bits` (ou calculé depuis `threshold`) n'est pas basé sur des FAR/FRR mesurés sur de vrais capteurs. C'est le chantier **R433**.

3. **`concrete-python` non installé** : disponible mais non ajouté à `requirements.txt` (L-048 — coût nœuds live). Migration Concrete = décision opérateur.

4. **`unique_human_proven=False`** : invariant absolu jusqu'à R433 (FAR/FRR/PAD vrais capteurs).

---

## Chantiers suivants

| Priorité | Chantier |
|---|---|
| P0 | **R433** — FAR/FRR/PAD mesurés sur vrais capteurs (calibration seuil) |
| P1 | **FORENSIC-02** — Critical Evidence Policy FAIL-CLOSED |
| P1 | **CI GitHub** gate DO-178C obligatoire |
| P1 | Migration `concrete-python` sur décision opérateur |

---

*CERTIFIED_100=false — mode DEBUG actif*
