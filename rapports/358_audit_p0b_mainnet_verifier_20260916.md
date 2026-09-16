# Rapport 358 — Corrections P0 post-audit + preuve vérificateur MAINNET

**Date :** 2026-09-16T08:30:00Z  
**SHA HEAD avant :** 798079c (main — rapport 357)  
**SHA HEAD après :** da58258 → push en cours  
**CERTIFIED_100 :** false — inchangé  
**Statut :** ✅ 95/95 tests PASS

---

## 1. Contexte

L'audit de l'assistant externe (session chat 16 sept. 2026) a identifié deux bugs P0
dans le code publié à `798079c`, ainsi qu'un point cryptographique à démontrer.
Ce rapport documente les corrections appliquées.

---

## 2. Bug P0-A — Namespace par nom implicite + non-idempotence

### Avant (798079c)

**`wallet_device_binding.py` — routage par nom :**

```python
# Ligne 127 — comportement incorrect
if wallet_namespace == "TEST" or is_test_wallet_name(wallet_name):
```

Problème : un appelant fournissant `wallet_name="test_quelque_chose"` sans
`wallet_namespace="TEST"` se retrouvait routé vers le registre TEST, changeant
implicitement la politique de sécurité à partir d'un champ de présentation.

**`_check_and_bind_test()` — doublon possible :**

```python
records.append(...)  # ajouté sans vérifier si la paire (wallet_name, fp) existait déjà
```

Appeler `bind(A, X)` trois fois créait trois entrées identiques dans le registre.

### Après (da58258)

**Routage par paramètre explicite uniquement :**

```python
# R358: routing par paramètre UNIQUEMENT, jamais par wallet_name
if wallet_namespace == "TEST":
```

**Idempotence PRODUCTION :**

```python
if existing:
    if existing["wallet_name"] == wallet_name:
        # R358 idempotence: same wallet+device already bound → no-op
        return
    raise WalletDeviceBindingError(...)
```

**Idempotence TEST :**

```python
if existing_same_pair:
    # R358 idempotence: exact same pair already recorded → no-op, no duplicate
    return
```

**`is_test_wallet_name()` :** conservée comme utilitaire d'information (logging/UI),
explicitement documentée comme non-influente sur le routage de sécurité.

### Tests ajoutés

| Test | Vérifie |
|------|---------|
| `test_namespace_by_explicit_parameter_not_by_name` | `artcbdev1…` sans `wallet_namespace="TEST"` → PRODUCTION |
| `test_production_bind_is_idempotent` | `bind(A,X)×2` → 1 enregistrement PROD |
| `test_test_bind_is_idempotent` | `bind(A,X)×3` → 1 enregistrement TEST |

---

## 3. Audit P0-B — Preuve que la signature TEST est rejetée par le vérificateur MAINNET

### Question de l'audit (§4)

> Le rapport dit « signature TEST mathématiquement invalide sur MAINNET ».
> Il faut démontrer que le **vérificateur** MAINNET reconstruit son propre message
> et rejette le message TEST, pas seulement que les messages sont différents.

### Analyse du code `chain/manager.py`

```python
# MAINNET signe (ligne 356)
def _sign_block(self, block_hash: str) -> str:
    message = block_hash.encode("utf-8")      # ex. "a3f7...c4" → bytes

# MAINNET vérifie (ligne 366)
def verify_block_signature(self, block_hash: str, signature: str) -> bool:
    message = block_hash.encode("utf-8")      # reconstruit le même message
    return verify_hybrid_and_or_window(message=message, ...)
```

Le message MAINNET est **toujours** `block_hash.encode()` — une chaîne hexadécimale.

### Message TEST

`TestWallet.sign_payload()` signe :

```json
{
  "domain_id":        "ARTCB/WALLET/TEST/V1",
  "network_id":       "artcb-testnet-1",
  "genesis_hash":     "genesis-artcb-testnet-1",
  "protocol_version": "189-testnet-1",
  "wallet_id":        "artcbdev1q...",
  "nonce":            0,
  "payload":          { ... }
}
```

Ces deux messages sont **structurellement incompatibles**. Le vérificateur MAINNET
reconstruit `block_hash.encode()` et vérifie la signature contre ce message — pas
contre l'enveloppe JSON TEST. Résultat : `BadSignatureError`.

### Tests de preuve

```python
# Test 1 — signature TEST sur message MAINNET → BadSignatureError
def test_test_signature_cannot_verify_as_mainnet_block_hash():
    fake_block_hash = "a" * 64
    mainnet_message = fake_block_hash.encode("utf-8")
    test_sig_hex = w.sign_payload({"action": "op"})   # signe l'enveloppe JSON TEST
    → verify(mainnet_message, test_sig_bytes) → BadSignatureError ✅

# Test 2 — signature MAINNET sur enveloppe TEST → BadSignatureError
def test_mainnet_block_signature_cannot_verify_as_test_payload():
    mainnet_signed = sk.sign(block_hash.encode())
    → verify(test_envelope_bytes, mainnet_sig) → BadSignatureError ✅

# Test 3 — verify_hybrid_and_or_window() avec message MAINNET + sig TEST → False
def test_verify_block_signature_rejects_test_sig():
    ok = verify_hybrid_and_or_window(
        message=mainnet_message,
        signature_value=f"ed25519:{test_sig_hex}",
        ...
    )
    assert not ok ✅
```

### Conclusion audit §4

La séparation est **cryptographiquement prouvée** par les messages différents.
Elle n'est pas seulement visuelle (préfixe `artcbdev`). Un attaquant ne peut pas
présenter une signature TEST à un nœud MAINNET et la faire accepter, car les messages
divergent structurellement.

---

## 4. Réponse aux points restants de l'audit

### §9 — Isolation économique complète

Confirmé comme backlog P1. `reject_cross_domain_transfer()` couvre les transferts
explicites. Chemins `reward/settlement/faucet` non encore connectés.

### §11 — CI `798079c`

La CI est configurée sur `push: branches: [main]` (commit `fa5d789`). Les runs CI
pour `798079c` et `da58258` sont déclenchés mais non encore lisibles via l'API GitHub
sans token étendu. Le résultat local est `95/95 PASS`.

### §15 — Race condition READ/CHECK/WRITE

Bogue préexistant, non introduit par TEST DOMAIN. Reste dans le backlog de sécurité.
La correction nécessite soit un lock fichier (`fcntl.flock`) soit une migration vers
un store atomique (SQLite/LMDB). Hors périmètre de ce rapport.

---

## 5. Résultats tests

```
95 passed, 5 warnings in 1.27s
```

| Catégorie | Avant | Après |
|-----------|-------|-------|
| Domain separation | 9 | 9 |
| State machine | 12 | 12 |
| Attestations | 11 | 11 |
| Factory profils | 17 | 17 |
| Factory adversariaux | 17 | 17 |
| Binding TEST | 8 | 10 (+2 idempotence) |
| Cross-domain policy | 13 | 13 |
| Signatures domain-séparées | 2 | 2 |
| **Vérificateur MAINNET (nouveau)** | **0** | **3** |
| `test_namespace_by_explicit_parameter` | 0 | 1 |
| **Total** | **90** | **95** |

---

## 6. État des 4 garanties après corrections

| Garantie | État |
|----------|------|
| `ARTCBDEV ≠ ARTCB` cryptographiquement | ✅ Démontré (H(TEST_TAG\|\|PK) ≠ H(MAIN_TAG\|\|PK)) |
| TEST ≠ MAINNET économiquement | ⚠️ Transferts couverts ; reward/settlement = backlog P1 |
| Signatures TEST ≠ MAINNET | ✅ **Prouvé** — messages structurellement différents, 3 tests de rejet |
| Validation non désactivée | ✅ Confirmé — namespace par paramètre explicite, moteur intact |

---

## 7. Commits

| SHA | Description |
|-----|-------------|
| `798079c` | feat(testdomain): TEST DOMAIN cryptographic separation — 90 tests |
| `da58258` | fix(testdomain): binding namespace explicite + idempotence — 92 tests |
| (ce push) | audit(testdomain): P0-B preuve vérificateur MAINNET — 95 tests |
