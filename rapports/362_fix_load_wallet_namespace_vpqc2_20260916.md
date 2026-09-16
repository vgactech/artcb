# Rapport 362 — Fix load_wallet() namespace + tests régression V-PQC-2

**Date** : 2026-09-16  
**Branche** : main  
**Base** : commit `171bb84` (V-PQC-2)

---

## 1. Bug corrigé

### Problème identifié par l'audit ChatGPT (rapports 353–356)

Dans `src/artcb/wallet/manager.py`, `load_wallet()` utilisait toujours le chemin
**legacy** pour recalculer `address_v2` :

```python
# AVANT (bug) — ligne 252
address_v2 = hybrid_address_v2(signing_key.verify_key.encode(), pqc_public)
```

Conséquence : un wallet TEST créé avec `artcb2t…` était **rechargé avec une `address_v2`
recalculée en `artcb2…`** (MAINNET legacy).

Incohérence create → store → reload :

| Opération | address_v2 |
|-----------|-----------|
| `create_wallet(wallet_namespace="TEST")` | `artcb2t…` ✅ |
| `load_wallet(name=...)` | `artcb2…` ❌ **MAINNET legacy** |

De même, `address` (Ed25519) était systématiquement recalculée via `address_from_signing_key()`
(chemin MAINNET) sans tenir compte du namespace stocké.

---

## 2. Correction appliquée

### `src/artcb/wallet/manager.py` — `load_wallet()`

**Ajout** : lecture de `wallet_namespace` depuis le `.json` metadata avant tout calcul d'adresse.

```python
# Read wallet_namespace from .json metadata (V-PQC-2 fix)
meta_path = self.wallet_dir / f"{name}.json"
stored_ns = "MAINNET"
if meta_path.is_file():
    try:
        meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
        stored_ns = meta_data.get("wallet_namespace", "MAINNET").upper().strip()
    except (json.JSONDecodeError, OSError):
        stored_ns = "MAINNET"
```

**address_v2 (PQC hybride)** :
```python
if stored_ns == "TEST":
    address_v2 = generate_test_hybrid_address_v2(
        signing_key.verify_key.encode(), pqc_public
    )  # → artcb2t…
else:
    address_v2 = hybrid_address_v2(signing_key.verify_key.encode(), pqc_public)
    # → artcb2… (legacy, backward compat)
```

**address (Ed25519)** :
```python
if stored_ns == "TEST":
    address = generate_test_address(signing_key.verify_key.encode())  # artcbdev1…
else:
    address = address_from_signing_key(signing_key)  # artcb1… legacy
```

**Fallback** : si le `.json` est absent ou corrompu → `stored_ns = "MAINNET"` (compatibilité
wallets legacy sans metadata).

---

## 3. Tests de régression ajoutés

### Classe `TestVPQC2LoadWalletRegression` dans `tests/test_vpqc2.py`

8 nouveaux tests couvrant :

| Test | Description |
|------|-------------|
| `test_reload_test_wallet_address_stays_artcbdev1` | Ed25519 TEST : create → reload conserve `artcbdev1…` |
| `test_reload_mainnet_wallet_address_stays_artcb1` | Ed25519 MAINNET : create → reload conserve `artcb1…` |
| `test_reload_test_wallet_address_v2_stays_artcb2t` | **Bug corrigé** : PQC TEST → reload toujours `artcb2t…` |
| `test_reload_mainnet_wallet_address_v2_stays_artcb2` | PQC MAINNET → reload toujours `artcb2…` (legacy) |
| `test_reload_address_equals_created_address` | address create == address reload |
| `test_reload_address_v2_equals_created_address_v2_test` | address_v2 TEST create == reload |
| `test_reload_address_v2_equals_created_address_v2_mainnet` | address_v2 MAINNET create == reload |
| `test_wallet_without_json_metadata_falls_back_mainnet` | .json absent → fallback MAINNET sans crash |

---

## 4. Résultats des tests

```
tests/test_vpqc2.py          30 passed  (22 existants + 8 nouveaux)
tests/test_testdomain.py     97 passed
tests/test_testdomain_e2e.py 53 passed
tests/test_testdomain_live_api.py 22 passed
─────────────────────────────────────
TOTAL                       202 passed  ✅
```

Note : `tests/test_api.py::test_store_and_chain` échoue sur `main` avant ces changements
(défaut préexistant, non introduit par ce commit).

---

## 5. Décision MAINNET legacy formalisée

Le chemin MAINNET utilise toujours `hybrid_address_v2()` (sans domain tag) pour préserver
la **compatibilité descendante** des adresses `artcb2…` déjà créées et enregistrées en
production. Migration progressive post-V-PQC-2 à planifier si nécessaire.

Commentaire dans le code :
```python
# V-PQC-2: recalculate address_v2 using the stored namespace
# TEST    → artcb2t… (domain-separated)
# MAINNET → artcb2…  (legacy, backward compat)
```

---

## 6. État CERTIFIED_100

`CERTIFIED_100 = false`

Trous restants (inchangés) :
- Déploiement OVH1 réel
- Propagation multi-nœuds confirmée
- Consensus PBFT distribué
- Persistance après redémarrage

---

## 7. Fichiers modifiés

| Fichier | Modification |
|---------|-------------|
| `src/artcb/wallet/manager.py` | Fix `load_wallet()` : lecture `wallet_namespace` depuis `.json` |
| `tests/test_vpqc2.py` | +8 tests `TestVPQC2LoadWalletRegression` |
| `rapports/362_fix_load_wallet_namespace_vpqc2_20260916.md` | Ce rapport |
