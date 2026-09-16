# Rapport 357 — TEST DOMAIN : implémentation complète

**Date :** 2026-09-16T08:09:14Z  
**SHA HEAD :** 9853e13d4dc5 (main)  
**CERTIFIED_100 :** false — inchangé  
**Statut :** ✅ 90/90 tests PASS

---

## 1. Contexte

Les rapports 353, 354, 355 et 356 (sessions ChatGPT) avaient produit des spécifications très détaillées pour un **TEST DOMAIN cryptographiquement séparé du MAINNET**. Aucune ligne de code n'avait encore été livrée.

Ce rapport documente l'implémentation complète ordonnée par l'utilisateur (GO — session 2026-09-16).

---

## 2. Fichiers créés / modifiés

### Avant / Après

| Fichier | Avant | Après |
|---------|-------|-------|
| `src/artcb/testdomain/__init__.py` | absent | créé — exports TEST DOMAIN |
| `src/artcb/testdomain/policy.py` | absent | créé — NETWORK_ID/GENESIS_HASH TEST, cross-domain reject |
| `src/artcb/testdomain/wallet_states.py` | absent | créé — WalletState enum + machine à états |
| `src/artcb/testdomain/attestation.py` | absent | créé — TestAttestationProvider |
| `src/artcb/testdomain/factory.py` | absent | créé — TestWalletFactory profils A..J + adversariaux |
| `src/artcb/wallet/address.py` | `generate_address()` sans domain tag | + `generate_address_with_domain_tag()`, `generate_test_address()`, `generate_mainnet_address_domain_separated()` |
| `src/artcb/security/wallet_device_binding.py` | 1 registre, pas de namespace TEST | + registre TEST séparé (`test_wallet_device_bindings.json`), `is_test_wallet_name()`, `_check_and_bind_test()` |
| `tests/test_testdomain.py` | absent | créé — 90 tests |

---

## 3. Invariants architecturaux implémentés

### 3.1 Domain separation cryptographique (rapport 354 §14, rapport 355 §4)

**Avant :**
```python
# MAINNET et TEST utilisaient le même hash
address = SHA256(pubkey) → RIPEMD160 → Bech32("artcb", …)
```

**Après :**
```python
# MAINNET : H("ARTCB/WALLET/MAINNET/V1" || pubkey)  → artcb1…
# TEST    : H("ARTCB/WALLET/TEST/V1"    || pubkey)  → artcbdev1…
# Même clé privée → adresses DIFFÉRENTES selon le domaine
address = generate_address_with_domain_tag(pk, domain_tag=TEST_DOMAIN_TAG, prefix="artcbdev")
```

**Preuve test :** `test_same_key_different_domain_yields_different_address` → PASS

---

### 3.2 Séparation protocolaire réseau (rapport 355 §8)

**Constantes TEST distinctes du MAINNET :**

| Paramètre | MAINNET | TEST |
|-----------|---------|------|
| `NETWORK_ID` | `artcb-mainnet-1` | `artcb-testnet-1` |
| `PROTOCOL_VERSION` | `189-mainnet-1` | `189-testnet-1` |
| `GENESIS_HASH` | `genesis-artcb-mainnet-1` | `genesis-artcb-testnet-1` |

Un pair MAINNET tentant de se connecter à un nœud TEST est rejeté par `accept_test_peer_protocol()`.

---

### 3.3 Machine à états wallet (rapport 353 §5, rapport 355 §27)

**17 états implémentés :**

```
KEY_ONLY → DEVICE_BOUND → IDENTITY_BOUND → IDENTITY_ATTESTED
  → CERT_10 → CERT_25 → CERT_50 → CERT_75 → CERT_100 → ACTIVE
  → SUSPENDED / EXPIRED / REVOKED / RECOVERY / ROTATION_PENDING / ROTATED / MATURE
```

**Transitions invalides rejetées :**
- `KEY_ONLY → CERT_100` : **REJETÉ** (étapes intermédiaires manquantes)
- `CERT_50 → ACTIVE` : **REJETÉ** (quorum insuffisant)
- `REVOKED → ACTIVE` : **REJETÉ** (doit passer par RECOVERY)
- `<adversarial> → anything` : **REJETÉ** (états terminaux)

---

### 3.4 TestAttestationProvider (rapport 354 §7)

Produit des attestations synthétiques déterministes :
- `TEST-HUMAN-000001`, `TEST-HUMAN-000002`, …
- Signées Ed25519 (vérifiables, pas mockées)
- `attestation_type = "TEST"` — jamais confondu avec `"HUMAN_UNIQUE"`
- Supporte : validité normale, `expired=True`, `revoked=True`

**Moteur de validation identique à la production** — seule la *source* des preuves diffère.

---

### 3.5 TestWalletFactory — 10 profils + 15 faults adversariaux (rapport 353 §10–§11)

| Profil | État | Description |
|--------|------|-------------|
| A | `KEY_ONLY` | Clé seule |
| B | `DEVICE_BOUND` | + appareil |
| C | `IDENTITY_BOUND` | + identité |
| D | `CERT_10` | 10/100 validateurs |
| E | `CERT_50` | 50/100 validateurs |
| F | `CERT_100` → `ACTIVE` | Quorum complet |
| G | `EXPIRED` | Attestation expirée |
| H | `REVOKED` | Identité révoquée |
| I | `INVALID_SIGNATURE` | Signature corrompue |
| J | `REPLAY` | Nonce rejoué |

**15 faults adversariaux :** `BAD_SIGNATURE`, `WRONG_DEVICE`, `EXPIRED`, `REVOKED`, `REPLAY`, `WRONG_NONCE`, `WRONG_VALIDATOR`, `DUPLICATE_VALIDATOR`, `INSUFFICIENT_QUORUM`, `WRONG_NETWORK`, `WRONG_GENESIS`, `WRONG_DOMAIN`, `UNAUTHORIZED_AGENT`, `WRONG_PRIVATE_KEY`, `WRONG_PUBLIC_KEY`

---

### 3.6 Signatures domain-séparées (rapport 355 §5–§7)

Chaque `sign_payload()` signe un envelope contenant :

```json
{
  "domain_id":         "ARTCB/WALLET/TEST/V1",
  "network_id":        "artcb-testnet-1",
  "genesis_hash":      "genesis-artcb-testnet-1",
  "protocol_version":  "189-testnet-1",
  "wallet_id":         "artcbdev1q…",
  "nonce":             0,
  "payload":           { … }
}
```

→ Une signature TEST est **mathématiquement invalide sur MAINNET** (network_id différent dans le message signé).

**Test :** `test_test_wallet_sign_includes_network_id_in_payload` → PASS

---

### 3.7 Registre wallet_device_binding TEST (rapport 354 §9, rapport 355 §22)

**Avant :**
```
ARTCB_ALLOW_MULTI_WALLET=true → désactive TOUTE la validation
```

**Après :**
```
wallet_namespace="TEST" → registre séparé (test_wallet_device_bindings.json)
                        → plusieurs wallets TEST par device autorisés
                        → validation engine INTACTE (pas de skip)
                        → PRODUCTION inchangée (1 wallet par device)
```

**Règle :** `test_namespace_stored_in_separate_file` → PASS  
**Règle :** `production_namespace_still_enforces_single_wallet` → PASS

---

### 3.8 Rejet cross-domain (rapport 353 §13, rapport 356 §14)

```python
reject_cross_domain_transfer("artcbdev1qsender", "artcb1qrecipient")
→ (True, "cross_domain_reject: TEST→MAINNET forbidden")

reject_cross_domain_transfer("artcb1qsender", "artcbdev1qrecipient")
→ (True, "cross_domain_reject: MAINNET→TEST forbidden")
```

---

## 4. Résultats tests

```
90 passed, 5 warnings in 1.31s
```

**5 warnings :** pytest collecte les classes `TestAttestation`, `TestAttestationProvider`, `TestWallet`, `TestWalletFactory` du code source (préfixe `Test*`) — warnings de collecte non-bloquants, aucun impact.

**Répartition des 90 tests :**

| Section | Tests |
|---------|-------|
| Domain separation address | 9 |
| Machine à états | 12 |
| TestAttestationProvider | 11 |
| TestWalletFactory profils | 17 |
| TestWalletFactory adversariaux | 17 |
| wallet_device_binding TEST | 8 |
| Cross-domain policy | 13 |
| Signatures domain-séparées | 2 |
| **Total** | **90** |

---

## 5. Ce qui reste à faire (backlog — non implémenté dans ce rapport)

Conformément à l'audit du rapport 355 §29 (colonne « À IMPLÉMENTER ») :

| Élément | Priorité |
|---------|---------|
| Intégration `POST /wallet/create` avec `wallet_namespace` param | P1 |
| TEST Genesis block (bloc 0 du testnet) | P1 |
| Ledger économique TEST isolé (`test_chain.jsonl`) | P1 |
| Intégration pipeline mining en mode TEST | P2 |
| API `GET /api/v1/testdomain/wallets` | P2 |
| V-PQC-2 (séparation adresse PQC par domain tag) | P2 |

---

## 6. Garanties non-négociables (rapport 353 §23)

```
1. ARTCBDEV ≠ ARTCB cryptographiquement        ✅ (domain tag dans hash)
2. TEST ≠ MAINNET économiquement               ✅ (reject_cross_domain_transfer)
3. TEST signatures ≠ MAINNET signatures        ✅ (network_id dans envelope)
4. TEST validation ≠ validation désactivée     ✅ (moteur identique, ARTCB_ALLOW_MULTI_WALLET non requis)
```
