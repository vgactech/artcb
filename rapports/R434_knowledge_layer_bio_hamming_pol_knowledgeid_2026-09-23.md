# R434 — Knowledge Layer ARTCD, BIO Hamming routing, PoL KnowledgeID

**Date :** 2026-09-23  
**Modules :** `src/artcb/knowledge/` (nouveau) · `biometric_onchain.py` · `pol/scorer.py`  
**Chantiers :** ARTCD / BIO / POL — travail simultané en parallèle  
**Statut :** ✅ DONE — 38/38 tests PASS  
**CERTIFIED_100 :** false

---

## Contexte — Les trois chantiers parallèles

R434 répond à la directive explicite : **travailler tous les chantiers simultanément**.  
Les chantiers R433 (sécurité binding/forensic) et R434 (ARTCD/BIO/POL) sont distincts mais complémentaires :

```
IDENTITÉ                    CONNAISSANCE / RAISONNEMENT
Human                              ARTCD
  ↓                                  ↓
Biometric/WebAuthn            KnowledgeID
  ↓                                  ↓
Device                        UsageID
  ↓                                  ↓
Wallet                     Useful Work → PoL
  ↓                                  ↓
Binding (R433)               Reward (→ R435+)
```

---

## Chantier A — Knowledge Layer (`src/artcb/knowledge/`)

**Avant R434 :** le répertoire `src/artcb/knowledge/` **n'existait pas**.  
**Après R434 :** 5 modules Python + package `__init__.py`.

### A1 — `knowledge.py` — KnowledgeRecord, KnowledgeID

```python
# Avant : inexistant
# Après :
rec = create_knowledge(reasoning_id="R_abc", producer_id="agent_A")
# → KnowledgeRecord(knowledge_id="K" + sha256[:24], status=ACTIVE, frozen=True)
```

**Invariant :** `knowledge_id` est **global et déterministe** — deux agents produisant le même raisonnement avec les mêmes paramètres obtiennent le même KnowledgeID.

Types : `REASONING`, `FACT`, `HYPOTHESIS`, `PROOF`, `COUNTER`, `COMPOSITION`, `FAILURE`, `CONDITION`, `DEPENDENCY`  
Statuts : `ACTIVE`, `SUPERSEDED`, `INVALIDATED`, `HYPOTHESIS`, `COMPOSED`

### A2 — `usage.py` — UsageRecord, UsageID

```python
# Avant : inexistant
# Après :
u = record_usage(knowledge_id="K_abc", consumer_id="agent_B", purpose=UsagePurpose.VALIDATION)
# → UsageRecord(usage_id="U" + sha256[:24], pol_eligible=True si ACTIVE+purpose éligible)
```

**Invariant PoL :** `pol_eligible=True` uniquement si `knowledge_status=="ACTIVE"` AND `purpose in POL_ELIGIBLE_PURPOSES`  
Purposes éligibles : `COMPOSITION`, `VALIDATION`, `DERIVATION`, `POL_CLAIM`

### A3 — `provenance.py` — ProvenanceChain, lignée cryptographique

```python
# Avant : inexistant
# Après :
chain = ProvenanceChain()
chain.add_link(make_link(from_id="K_A", to_id="K_B", transformation=Transformation.DERIVATION, actor_id="a"))
chain.seal()  # append-only
chain_hash = chain.chain_hash()  # sha256(link_id[0] || link_id[1] || …)
```

`chain_hash()` invalide si réordonnancement ou altération d'un maillon.  
`verify()` détecte les sauts dans la lignée.  
`ancestors(kid)` remonte la lignée.

### A4 — `composition.py` — compose_knowledge()

```python
# Avant : inexistant
# Après :
result = compose_knowledge(parent_records=[rec_A, rec_B], producer_id="p", reasoning_id="R_comp")
# → CompositionResult(composed_record, provenance_chain, usage_records, all_parents_active)
```

Si un parent est `SUPERSEDED` → `all_parents_active=False` → `status=HYPOTHESIS` (prudence).

### A5 — `store.py` — KnowledgeStore

Persistance JSON atomique (R433 pattern : `fcntl.LOCK_EX` + tmp → fsync → rename).  
Méthodes : `save()`, `get()`, `list_active()`, `search_by_reasoning()`, `save_usage()`, `list_usages()`, `pol_eligible_usages()`.

---

## Chantier B — BIO Hamming routing dans `check_uniqueness()`

**Avant R434 (R376) :**
```python
# Routing à 2 niveaux
if template_bytes_for_match:
    → privacy_preserving_xor (XOR sur SHA-256 — effet avalanche)
else:
    → exact_hash
```

**Après R434 :**
```python
# Routing à 3 niveaux (priorité décroissante)
if template_bytes_for_match:
    if any(rec a template_bytes_b64 ou template_bytes_hex):
        → hamming_direct  ← NOUVEAU (R434) — pas d'effet avalanche
    else:
        → privacy_preserving_xor  (R376 — fallback)
else:
    → exact_hash
```

**Nouveau paramètre :** `threshold_bits: int | None` — seuil absolu Hamming en bits (prime sur `threshold`).

**Invariants maintenus :** `unique_human_proven=False` + `certified=False` sur les **3 chemins**.

---

## Chantier C — PoL KnowledgeID dans `PolMetrics`

**Avant (src : `pol/scorer.py` ligne 18) :**
```python
@dataclass(frozen=True)
class PolMetrics:
    delta_compression: float
    validation_rate: float
    retrieval_accuracy: float
    pol_score: float
    block_accepted: bool
    # → pas de lien ARTCD
```

**Après (R434) :**
```python
@dataclass(frozen=True)
class PolMetrics:
    delta_compression: float
    validation_rate: float
    retrieval_accuracy: float
    pol_score: float
    block_accepted: bool
    knowledge_id: str | None = None   # ← R434
    usage_id: str | None = None       # ← R434
```

`to_dict()` n'inclut `knowledge_id`/`usage_id` **que si non None** (backward-compatibilité).

```python
metrics = scorer.score(graph, knowledge_id="K_abc", usage_id="U_xyz")
# → metrics.to_dict() inclut knowledge_id et usage_id
```

---

## Fichiers créés/modifiés

| Fichier | Nature | Avant | Après |
|---------|--------|-------|-------|
| `src/artcb/knowledge/__init__.py` | Nouveau | ❌ | ✅ |
| `src/artcb/knowledge/knowledge.py` | Nouveau | ❌ | ✅ MODULE_VERSION `1.0.0` |
| `src/artcb/knowledge/usage.py` | Nouveau | ❌ | ✅ MODULE_VERSION `1.0.0` |
| `src/artcb/knowledge/provenance.py` | Nouveau | ❌ | ✅ MODULE_VERSION `1.0.0` |
| `src/artcb/knowledge/composition.py` | Nouveau | ❌ | ✅ MODULE_VERSION `1.0.0` |
| `src/artcb/knowledge/store.py` | Nouveau | ❌ | ✅ MODULE_VERSION `1.0.0` |
| `src/artcb/identity/biometric_onchain.py` | Modifié | routing 2 niveaux | routing 3 niveaux + `threshold_bits` |
| `src/artcb/pol/scorer.py` | Modifié | pas de KnowledgeID | `knowledge_id` + `usage_id` dans `PolMetrics` |
| `tests/test_r434_knowledge_bio_pol.py` | Nouveau | ❌ | ✅ 38 tests |

---

## Résultats des tests

### Nouveaux tests R434 — 38/38 PASS

| Groupe | Tests | Résultat |
|--------|-------|---------|
| Knowledge Layer (K-01→K-07) | 7/7 | ✅ |
| Usage (U-01→U-06) | 6/6 | ✅ |
| Provenance (P-01→P-05) | 5/5 | ✅ |
| Composition (C-01→C-05) | 5/5 | ✅ |
| Store (S-01→S-06) | 6/6 | ✅ |
| BIO Hamming routing (B-01→B-06) | 6/6 | ✅ |
| PoL KnowledgeID (L-01→L-03) | 3/3 | ✅ |

### Non-régression — 76/76 PASS

| Suite | Tests | Résultat |
|-------|-------|---------|
| R433 transactionnel | 15/15 | ✅ |
| R431 revoke with history | 9/9 | ✅ |
| R432 binding security | 12/12 | ✅ |
| R345 wallet client | 2/2 | ✅ |
| R434 knowledge/bio/pol | 38/38 | ✅ |

---

## Architecture ARTCB après R434

```
ARTCB
  │
  ├── IDENTITÉ (R431/R432/R433)
  │     WalletDeviceBindingStore
  │     RevocationHistory + PurgeLog forensic enchaîné
  │
  ├── BIOMÉTRIE (R372→R378 + R434)
  │     check_uniqueness() : hamming_direct > XOR > exact_hash
  │     BCH(255,191,8) FuzzyExtractor
  │
  ├── KNOWLEDGE / ARTCD (R434)
  │     KnowledgeRecord → KnowledgeID (global, déterministe)
  │     UsageRecord → UsageID + pol_eligible
  │     ProvenanceChain → lignée cryptographique hash-chainée
  │     compose_knowledge() → CompositionResult
  │     KnowledgeStore → persistance atomique
  │
  └── PoL (R434)
        PolMetrics.knowledge_id → lien ARTCD → PoL
        PolMetrics.usage_id → traçabilité UsageRecord → reward
```

---

## Limites documentées

- `knowledge_id` est déterministe **sur les paramètres fournis** — deux agents avec des timestamps différents produiront des IDs différents même pour le même raisonnement. Impliquer `reasoning_id` + `producer_id` + `type` + `parent_ids` suffit pour la détection de doublons inter-agents seulement si le même `created_at` est utilisé.
- `KnowledgeStore` utilise JSON plat — pas indexé. Pour scale > 10k entrées, migrer vers SQLite ou un store adapté.
- Hamming routing dans `check_uniqueness()` : `threshold_ratio = 1.0 - threshold` est une heuristique — doit être calibré sur capteurs réels (NIST BSSR). `CERTIFIED_100=false`.
- `PoL → Reward` : le lien `KnowledgeID → PolMetrics` est traçable mais le **règlement on-chain** reste à implémenter (R435+).
- Chantiers encore ouverts : FAR/FRR capteurs réels, anti-Sybil `wallet_per_human_limit` dans le pipeline enroll, ARTCD inter-agents live, TASK-006-LIVE-VALIDATION.

---

## Chantiers suivants (simultanés)

- **R435** : `wallet_per_human_limit` anti-Sybil dans le pipeline biométrique (R373 → enroll)
- **R436** : chaîne complète `KnowledgeID → WorkID → PoL → on-chain` (règlement)
- **TASK-006-LIVE-VALIDATION** : tests live N2/N4/N3
- **ARTCD inter-agents** : test de réutilisation/composition entre deux agents réels
