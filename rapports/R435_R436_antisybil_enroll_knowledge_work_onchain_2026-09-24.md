# R435 — Anti-Sybil gate dans `enroll_biometric()` + R436 — KnowledgeID → WorkID → PoL → on-chain

**Date :** 2026-09-24  
**Modules :** `src/artcb/identity/biometric_onchain.py` · `src/artcb/chain/knowledge_work.py`  
**Chantiers :** TASK-001-BIOMETRIE-SUITE (anti-Sybil) · ARTCD Knowledge Layer (chaîne PoL → on-chain)  
**Statut :** ✅ DONE — 28/28 tests nouveaux PASS | 245/245 total PASS  
**Commits :** `7253ede` (R435+R436) · `5bbd5ed` (R435-fp fingerprint)  
**SHA origin/main :** `5bbd5ed`  
**CERTIFIED_100 :** false

---

## Contexte

R435 et R436 sont les suites directes de R434 (Knowledge Layer ARTCD), selon les chantiers identifiés dans le rapport R434 :

```
R434 (R433+R432+R431 avant)
     │
     ├── R435 : anti-Sybil gate dans enroll_biometric()
     │         wallet_per_human_limit → CASE_3 TASK-001
     │
     └── R436 : KnowledgeID → WorkID → PoL → on-chain
               KnowledgeWorkRecord (PENDING → SEALED + block_hash)
```

---

## R435 — Anti-Sybil gate dans `enroll_biometric()`

### Problème avant R435

`enroll_biometric()` créait un `HumanIdentityRecord` avec `wallet_address` sans vérifier si ce `human_id` avait déjà un wallet économique actif. La logique anti-Sybil CASE_3 était dans `human_identity_policy.py` mais **non connectée** au pipeline biométrique.

### Solution R435

**Avant (src : `biometric_onchain.py` ligne 532) :**
```python
# Avant R435 — signature
def enroll_biometric(
    template_bytes: bytes,
    *,
    wallet_address: str | None = None,
    node_id: str | None = None,
    salt: bytes | None = None,
) -> tuple[BiometricEnrollmentResult, str, str]:
    # ...
    record = HumanIdentityRecord(wallet_address=wallet_address, ...)
    result = BiometricEnrollmentResult(status="enrolled", ...)
```

**Après R435 :**
```python
# Après R435 — gate anti-Sybil intégré
def enroll_biometric(
    template_bytes: bytes,
    *,
    wallet_address: str | None = None,
    node_id: str | None = None,
    salt: bytes | None = None,
    blinding: bytes | None = None,          # ← NOUVEAU (déterminisme tests)
    existing_wallet_links: list[dict] | None = None,  # ← NOUVEAU (gate Sybil)
) -> tuple[BiometricEnrollmentResult, str, str]:
    # ...
    # Gate anti-Sybil CASE_3 — après dérivation du human_id
    if wallet_address is not None and existing_wallet_links is not None:
        limit_decision = check_wallet_per_human_limit(human_id, existing_wallet_links)
        if not limit_decision.allowed:
            sybil_blocked = True   # → wallet_address retiré du record

    result = BiometricEnrollmentResult(
        status="sybil_blocked" if sybil_blocked else "enrolled",
        sybil_blocked=sybil_blocked,        # ← NOUVEAU
        sybil_reason=sybil_reason,          # ← NOUVEAU
        existing_wallet=existing_wallet,    # ← NOUVEAU
    )
```

### Comportement du gate (3 chemins)

| Condition | Comportement |
|-----------|-------------|
| `existing_wallet_links=None` | Pas de vérification (compat ascendante) |
| `wallet_address=None` | Pas de vérification (pas d'association demandée) |
| `wallet_address` fourni + links + human_id déjà actif | `sybil_blocked=True`, `status="sybil_blocked"`, `wallet_address=None` dans le record |

### Champ `BiometricEnrollmentResult` ajoutés

| Champ | Type | Description |
|-------|------|-------------|
| `sybil_blocked` | `bool` | True si CASE_3 déclenché |
| `sybil_reason` | `str \| None` | Message "human_wallet_limit_reached…" |
| `existing_wallet` | `str \| None` | Wallet déjà actif pour ce HumanID |

### Invariants maintenus

- `unique_human_proven=False` dans **tous** les chemins (invariant absolu)
- `sybil_blocked=True` → `wallet_address=None` dans `human_identity_record` (on-chain safe)
- Compat ascendante : sans `existing_wallet_links`, comportement identique à avant R435

---

## R436 — KnowledgeID → WorkID → PoL → on-chain

### Problème avant R436

La chaîne `KnowledgeID → PolMetrics` (R434) ne possédait pas de maillon reliant le bloc on-chain (block_hash). Un bloc inscrit n'était pas traçable vers son KnowledgeRecord producteur.

### Solution R436 — Nouveau module `src/artcb/chain/knowledge_work.py`

Crée un `KnowledgeWorkRecord` immuable (frozen=True) qui attache :
- un **KnowledgeID ARTCD** → à un **WorkID économique** → à un **bloc on-chain**
- Cycle de vie : `PENDING` (bloc non inscrit) → `SEALED` (block_hash présent)

```
KnowledgeRecord (knowledge.py)
      ↓ knowledge_id
UsageRecord (usage.py)
      ↓ usage_id + pol_eligible
PolMetrics (scorer.py)
      ↓ pol_score + block_accepted + knowledge_id + usage_id
KnowledgeWorkRecord  ← R436 (knowledge_work.py)
      ↓ work_record_id + pol_score + block_hash
Blockchain on-chain (chain/manager.py)
```

**Avant R436 :** `src/artcb/chain/knowledge_work.py` **n'existait pas**.

**Après R436 :**
```python
rec = create_knowledge_work_record(
    knowledge_id="K_abc",
    work_id="work_xyz",
    pol_score=0.72,
    block_accepted=True,
    usage_id="U_def",
    producer_id="agent_A",
)
# → KnowledgeWorkRecord(work_record_id="KW...", status="PENDING", block_hash=None)

store = KnowledgeWorkStore(data_dir=Path("data/knowledge_work"))
store.save(rec)

# Après inscription on-chain :
sealed = store.seal_with_block_hash(rec.work_record_id, block_hash="0x1a2b…")
# → KnowledgeWorkRecord(status="SEALED", block_hash="0x1a2b…")
```

### Propriétés du `work_record_id`

`work_record_id = "KW" + sha256(knowledge_id + work_id + pol_score + created_at)[:24]`

**Déterministe** — deux agents créant le même (knowledge_id, work_id, pol_score, created_at) obtiennent le même ID → déduplication inter-agents possible.

### `KnowledgeWorkStore` — Persistance atomique

Identique au pattern R433/R434 (fcntl.LOCK_EX + tmp → fsync → rename) :

| Méthode | Description |
|---------|-------------|
| `save(record)` | Upsert par work_record_id |
| `get(work_record_id)` | Lecture par ID |
| `list_pending()` | Records non encore inscrits on-chain |
| `list_sealed()` | Records inscrits on-chain |
| `list_by_knowledge_id(kid)` | Records liés à un KnowledgeID |
| `seal_with_block_hash(id, hash)` | PENDING → SEALED (ValueError si déjà SEALED) |

### Validations internes

- `pol_score` hors [0.0, 1.0] → `ValueError`
- `knowledge_id` vide → `ValueError`
- `work_id` vide → `ValueError`
- Double seal → `ValueError("déjà SEALED")`
- Seal record inexistant → `ValueError("introuvable")`

---

## Fichiers créés/modifiés

| Fichier | Nature | Avant | Après |
|---------|--------|-------|-------|
| `src/artcb/identity/biometric_onchain.py` | Modifié | `enroll_biometric()` sans gate Sybil | Gate anti-Sybil CASE_3 + `blinding` param |
| `src/artcb/chain/knowledge_work.py` | **Nouveau** | ❌ | ✅ `MODULE_VERSION 1.0.1` |
| `tests/test_r435_antysybil_enroll.py` | **Nouveau** | ❌ | ✅ 10 tests A01→A10 |
| `tests/test_r436_knowledge_work_onchain.py` | **Nouveau** | ❌ | ✅ 18 tests W01→W18 |

---

## Résultats des tests

### Nouveaux tests R435 — 10/10 PASS

| Test | Description | Résultat |
|------|-------------|---------|
| A01 | Sans existing_wallet_links → pas de vérification | ✅ |
| A02 | Premier enrôlement, links vides → autorisé | ✅ |
| A03 | Deuxième enrôlement même human_id → BLOQUÉ | ✅ |
| A04 | Sans wallet_address → pas de gate même avec links | ✅ |
| A05 | Wallet révoqué ne bloque pas | ✅ |
| A06 | Templates différents → human_ids distincts → pas de conflit | ✅ |
| A07 | unique_human_proven=False dans tous les chemins | ✅ |
| A08 | Même template+salt+blinding → même human_id (déterminisme) | ✅ |
| A09 | sybil_blocked=True → wallet_address absent du record on-chain | ✅ |
| A10 | Sans salt fixé → secrets distincts | ✅ |

### Nouveaux tests R436 — 18/18 PASS

| Groupe | Tests | Résultat |
|--------|-------|---------|
| Création PENDING (W01→W06) | 6/6 | ✅ |
| Sérialisation (W07) | 1/1 | ✅ |
| Seal / immutabilité (W08→W10) | 3/3 | ✅ |
| Store CRUD (W11→W17) | 7/7 | ✅ |
| Pipeline complet PoL→KW (W18) | 1/1 | ✅ |

### Non-régression — 217/217 PASS

| Suite | Tests | Résultat |
|-------|-------|---------|
| R434 knowledge/bio/pol | 38/38 | ✅ |
| R433 transactionnel forensic | 15/15 | ✅ |
| R432 binding security | 12/12 | ✅ |
| R431 revoke with history | 9/9 | ✅ |
| R430 G16 14 langues | 14/14 | ✅ |
| TASK-001 biometric | 94/94 | ✅ |
| R373 human identity policy | 26/26 | ✅ |
| R374 BCH | 30/30 | ✅ |
| R376 uniqueness | 22/22 | ✅ |
| R378 hamming | 28/28 | ✅ |

**Total R435+R436 + non-régression : 245/245 PASS**  
**Gate DO-178C (hook pre-commit) : 124/124 PASS ✅**

---

## Traçabilité commits

| SHA | Description |
|-----|-------------|
| `7253ede` | R435+R436 : anti-Sybil gate + KnowledgeWork module |
| `5bbd5ed` | R435-fp : fingerprint régénéré sur 7253ede (259 modules) |

Vérification fingerprint (L-053) : `logs/R394_module_fingerprints.json` → `git_sha=7253ede` ✅

---

## Architecture ARTCB après R435+R436

```
ARTCB
  │
  ├── IDENTITÉ (R431/R432/R433)
  │     WalletDeviceBindingStore
  │     RevocationHistory + PurgeLog forensic enchaîné
  │
  ├── BIOMÉTRIE (R372→R378 + R434 + R435)
  │     enroll_biometric() → gate anti-Sybil CASE_3 (R435)
  │     check_uniqueness() : hamming_direct > XOR > exact_hash
  │     BCH(255,191,8) FuzzyExtractor
  │     check_wallet_per_human_limit() BRANCHÉ dans le pipeline
  │
  ├── KNOWLEDGE / ARTCD (R434)
  │     KnowledgeRecord → KnowledgeID (global, déterministe)
  │     UsageRecord → UsageID + pol_eligible
  │     ProvenanceChain → lignée cryptographique hash-chainée
  │     compose_knowledge() → CompositionResult
  │     KnowledgeStore → persistance atomique
  │
  ├── PoL (R434)
  │     PolMetrics.knowledge_id → lien ARTCD → PoL
  │     PolMetrics.usage_id → traçabilité UsageRecord → reward
  │
  └── CHAIN / WORK (R436)
        KnowledgeWorkRecord → PENDING → SEALED + block_hash
        KnowledgeWorkStore → persistance atomique R433-pattern
        work_record_id = "KW" + sha256(kid+wid+pol+ts)[:24]
        Chaîne complète : KnowledgeID → WorkID → PoL → bloc
```

---

## Limites documentées

- **Gate Sybil R435** : le gate ne s'active que si `existing_wallet_links` est explicitement fourni. L'appelant (route API biométrique) doit charger via `load_wallet_human_links()` — non encore intégré dans les routes FastAPI (R437+).
- **`blinding` dans `enroll_biometric()`** : exposé pour les tests de déterminisme. En production, laisser `None` (généré aléatoirement).
- **R436 chaîne on-chain** : `KnowledgeWorkRecord.block_hash` est inscrit manuellement par l'appelant via `seal_with_block_hash()`. L'intégration automatique avec `chain/manager.py` lors d'un `add_block()` reste à faire (R437+).
- **FAR/FRR capteurs réels** : toujours non mesurés sur NIST BSSR. CERTIFIED_100=false.
- **`unique_human_proven=False`** : invariant absolu maintenu dans tous les chemins.

---

## Chantiers suivants

- **R437** : intégration `existing_wallet_links` dans les routes FastAPI (`/biometric/enroll`) + `seal_with_block_hash()` automatique lors de `add_block()`
- **TASK-006-LIVE-VALIDATION** : tests live N2/N4/N3
- **ARTCD inter-agents** : test de composition entre deux agents réels
- **FAR/FRR sur capteurs réels** : NIST BSSR calibration
