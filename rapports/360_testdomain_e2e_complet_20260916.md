# Rapport 360 — TEST DOMAIN E2E : bout en bout complet

**Date :** 2026-09-16T09:30:00Z  
**SHA HEAD :** 8a46ec0 (avant commit) → nouveau commit  
**CERTIFIED_100 :** false — inchangé  
**Statut :** ✅ 150/150 tests PASS (97 anciens + 53 nouveaux E2E)

---

## 1. Contexte

Le rapport de session 2026-09-16 (audit ChatGPT du commit `8a46ec0`) avait identifié 3 trous critiques dans l'implémentation TEST DOMAIN :

| Trou | Description |
|---|---|
| **T1** | `TEST_GENESIS_HASH` = identifiant déclaratif, pas un Genesis réel |
| **T2** | `/wallet/create` toujours MAINNET — pas de `wallet_namespace` |
| **T3** | Ledger TEST inexistant — `test_chain.jsonl` non créé |

Ce rapport documente la fermeture complète de ces trois trous.

---

## 2. Fichiers créés / modifiés

| Fichier | Action | Description |
|---------|--------|-------------|
| `src/artcb/testdomain/chain.py` | créé | `TestChainManager` — ledger TEST isolé |
| `src/artcb/testdomain/transaction.py` | créé | Transactions domain-séparées + validation + PoL |
| `src/artcb/testdomain/__init__.py` | modifié | Exports nouveaux modules |
| `src/artcb/wallet/manager.py` | modifié | `create_wallet(wallet_namespace=)` |
| `src/api/routes.py` | modifié | `CreateWalletRequest.wallet_namespace` |
| `tests/test_testdomain_e2e.py` | créé | 53 tests E2E (phases A→F) |

---

## 3. Phase A — TestChainManager (`test_chain.jsonl` isolé)

### Genesis réel

```python
# hash déterministe incluant TEST_NETWORK_ID dans le digest
gh = _build_test_block_hash(
    index=0, timestamp="2026-09-16T00:00:00Z",
    prev_hash="0"*64, network_id="artcb-testnet-1", ...
)
```

**Différence avec MAINNET :** le hash inclut `network_id=artcb-testnet-1` dans le matériau signé → un Genesis TEST ≠ Genesis MAINNET pour le même payload.

### Isolation physique

```text
MAINNET:  data/chain.jsonl
TEST:     data/test_chain.jsonl
```

**Invariant codé :** `assert mgr.blocks_path.name != "chain.jsonl"` — impossible d'instancier TestChainManager sur le fichier MAINNET.

### Validations enforced

| Rejection | Raison |
|---|---|
| `reject_wrong_network_id` | network_id ≠ artcb-testnet-1 |
| `reject_mainnet_block_in_test_chain` | domain == "MAINNET" |
| `reject_wrong_genesis_hash` | genesis_hash == mainnet hash |
| `reject_mainnet_contributor_in_test_block` | adresse artcb1… dans contributors |
| `reject_wrong_asset` | asset == "ARTCB" (production) |

---

## 4. Phase B — `/wallet/create` avec `wallet_namespace`

### API

```json
POST /wallet/create
{
  "name": "alice-test",
  "password": "...",
  "wallet_namespace": "TEST"
}
```

Réponse :
```json
{
  "address": "artcbdev1q...",
  "wallet_namespace": "TEST",
  "domain": "TEST",
  "asset": "tARTCB"
}
```

### Règle de dérivation d'adresse

```text
wallet_namespace="MAINNET" → address_from_signing_key()  → artcb1…
wallet_namespace="TEST"    → generate_test_address()     → artcbdev1…

H("ARTCB/WALLET/TEST/V1" || pubkey) ≠ H(pubkey seul)
```

**Le namespace est TOUJOURS un paramètre explicite — jamais déduit du nom du wallet** (règle R358 §5 préservée).

### Métadonnées

```json
{
  "wallet_namespace": "TEST",
  "domain": "TEST"
}
```

Stockées dans `{name}.json` — auditables.

---

## 5. Phase C — Transaction TEST domain-séparée

### Enveloppe signée

```json
{
  "domain_id": "ARTCB/WALLET/TEST/V1",
  "network_id": "artcb-testnet-1",
  "genesis_hash": "genesis-artcb-testnet-1",
  "protocol_version": "189-testnet-1",
  "wallet_id": "artcbdev1q...",
  "nonce": 0,
  "payload": {...},
  "asset": "tARTCB"
}
```

→ **Signature = Ed25519(SHA-256(canonical_json(envelope)))**

Une même clé privée produit une signature DIFFÉRENTE sur TEST vs MAINNET car le `network_id` dans le message signé diffère.

### Validations enforced

| Cas | Résultat |
|---|---|
| Signature correcte | VALID |
| Signature corrompue | reject_invalid_signature |
| network_id mainnet | reject_wrong_network_id |
| wallet_id = artcb1… | reject_non_test_wallet |
| recipient = artcb1… | cross_domain_reject: TEST→MAINNET |
| genesis_hash mainnet | reject_wrong_genesis_hash |

---

## 6. Phase D — Mining TEST (PoL + reward tARTCB + balance)

### Pipeline

```text
transactions TEST
      ↓
build_test_block_from_transactions()
      ↓
contributors = [{address: artcbdev1…, reward_satoshi: 100_000_000, asset: tARTCB}]
      ↓
TestChainManager.append_block()
      ↓
test_chain.jsonl ← bloc écrit
      ↓
get_balance(artcbdev1…)
      ↓
{balance_satoshi: 100_000_000, balance_tartcb: 1.0, asset: "tARTCB", mainnet_balance: None}
```

`mainnet_balance: None` — isolation économique explicite dans la réponse.

---

## 7. Phase E — Test E2E bout en bout

### Scénario `test_full_e2e_wallet_to_reward`

```text
1. SK → generate_test_address(pk)     → artcbdev1q…  ✅
2. build_test_transaction(…nonce=0)   → tx signée    ✅
3. validate_test_transaction(tx)      → valid=True   ✅
4. build_test_block_from_transactions → block_payload ✅
5. TestChainManager.append_block()    → index=1       ✅
6. get_balance(artcbdev1…)            → 1.0 tARTCB    ✅
7. data/chain.jsonl absent            → MAINNET intact ✅
```

### Scénario `test_mainnet_chain_isolated`

5 blocs TEST créés → `test_chain.jsonl` height=6, `chain.jsonl` absent ✅

---

## 8. Phase F — Tests adversariaux E2E

| Attaque | Rejet |
|---|---|
| Signature TEST → vérificateur MAINNET | `BadSignatureError` (message différent) |
| Transaction MAINNET → validateur TEST | `reject_wrong_network_id` |
| Bloc MAINNET → TestChainManager | `reject_wrong_network_id` |
| Bloc domain=MAINNET → TestChainManager | `reject_mainnet_block_in_test_chain` |
| Transfert TEST→MAINNET | `cross_domain_reject: TEST→MAINNET forbidden` |
| Transfert MAINNET→TEST | `cross_domain_reject: MAINNET→TEST forbidden` |
| Pair MAINNET sur nœud TEST | `network_id_mismatch` |
| Balance artcb1… dans TestChainManager | `reject_mainnet_address` |
| Signature corrompue | `reject_invalid_signature` |
| Mauvaise clé publique | `reject_invalid_signature` |
| Replay nonce=0 payload différent | hashes différents → détectable |
| genesis_hash mainnet dans tx | `reject_wrong_genesis_hash` |

---

## 9. Résultats tests

```
150 passed in 2.87s

  97  tests existants (test_testdomain.py) — inchangés ✅
  53  tests E2E nouveaux (test_testdomain_e2e.py)
     - 15 Phase A (TestChainManager)
     -  7 Phase B (WalletManager namespace)
     -  7 Phase C (Transaction)
     -  7 Phase D (Mining / balance)
     -  3 Phase E (E2E bout en bout)
     - 14 Phase F (adversariaux)
```

---

## 10. État des garanties (rapport 353 §23 + audit session)

| Garantie | Avant ce rapport | Après |
|---|---|---|
| ARTCBDEV ≠ ARTCB cryptographiquement | ✅ (R357) | ✅ |
| TEST ≠ MAINNET économiquement | ✅ (reject_cross_domain) | ✅ + ledger séparé |
| TEST signatures ≠ MAINNET signatures | ✅ (R357) | ✅ + prouvé E2E |
| TEST validation ≠ validation désactivée | ✅ (R357) | ✅ + validations E2E |
| Genesis TEST réel | ❌ (déclaratif) | **✅ bloc 0 réel** |
| test_chain.jsonl isolé | ❌ | **✅ implémenté** |
| /wallet/create → TEST | ❌ | **✅ wallet_namespace param** |
| Ledger balance tARTCB | ❌ | **✅ get_balance() TEST** |
| E2E wallet → tx → block → reward | ❌ | **✅ test_full_e2e_wallet_to_reward** |

---

## 11. Backlog restant (non implémenté dans ce rapport)

| Élément | Priorité |
|---|---|
| Intégration pipeline mining en mode TEST (nœud réel) | P2 |
| API `GET /api/v1/testdomain/wallets` | P2 |
| V-PQC-2 (adresse PQC domain-séparée) | P2 |
| Race condition wallet_device_binding (READ→WRITE sans lock distribué) | dette |
| TestChainManager ↔ PBFT failover isolation | P2 |
| Reward model TEST (actuellement fixe 1 tARTCB, pas PoL complet) | P2 |

`CERTIFIED_100 = false` — inchangé.
