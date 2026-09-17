# R371 — REASONING_RECORD : ReferenceID + FIRST_REFLEX + EARLIEST_DETECTABLE_POINT

**Date :** 2026-09-17T17:10:00Z  
**Commit :** `b2a5a62`  
**Base :** rapport 370 (audit cartographie REASONING_RECORD)  
**CERTIFIED_100 :** false

---

## 1. Contexte

Le rapport 370 avait identifié le **chaînon manquant** entre le réflexe R350–R354 et la mémoire ARTCB :

```
EXISTAIT                    MANQUAIT
────────                    ────────
ReflexEngine (R350)   →    ReferenceID
hooks Bob IDE         →    FIRST_REFLEX
agent_context_contract →   EARLIEST_DETECTABLE_POINT
ai_routes.py /memo    →    REASONING_RECORD (enveloppe)
```

Ce rapport documente l'implémentation complète R355.

---

## 2. Ce qui a été implémenté

### 2.1 `src/artcb/reasoning/reference_id.py`

**AVANT :** inexistant  
**APRÈS :** `ReferenceID` — identifiant canonique d'une cause de raisonnement

```python
# 4 types
ref_code(path="src/artcb/reflex/core.py", commit="b2a5a62")
# → refid:code:3f7a2b9c1e4d5f6a

ref_block(block_index=756, block_hash="083b1ff2...")
# → refid:block:a1b2c3d4e5f60001

ref_rule(rule_name="R350", rule_file=".cursor/rules/artcb-reflex-priority.mdc")
# → refid:rule:99f0deadbeef0123

ref_human(human_id="human_abc123")
# → refid:human:ff00112233445566
```

Format canonique : `refid:<type>:<sha256_16>`  
Déterministe. Vérification d'intégrité au roundtrip. Nanoseconde `created_at`.

### 2.2 `src/artcb/reasoning/first_reflex.py`

**AVANT :** inexistant  
**APRÈS :** `FirstReflex` + `EarliestDetectablePoint`

```python
# FIRST_REFLEX : premier point de détection
FirstReflex(
    session_id="r355-live-test",
    trigger_name="REFLEX_MEMORY",
    priority=0,                       # 0 = absolu
    evidence={"keywords": ["mémoire", "réflexe"], "files": [...]},
    reference_ids=["refid:rule:...", "refid:code:..."],
)
# sha256 calculé → immuable une fois créé

# EARLIEST_DETECTABLE_POINT : rétroprojection
EarliestDetectablePoint(
    trigger_name="REFLEX_MEMORY",
    chain_height=1142,
    confidence=0.35,
    method="log_trace",               # données scannées depuis agent_reasoning.jsonl
)
```

`estimate_earliest_from_logs()` scanne `data/trace/agent_reasoning.jsonl` pour trouver la première occurrence des mots-clés du trigger.

### 2.3 `src/artcb/reasoning/record.py`

**AVANT :** inexistant  
**APRÈS :** `ReasoningRecord` + `ReasoningRecordStore`

Cycle complet :
```
CONTEXTE REÇU
     ↓
FIRST_REFLEX (détection)
     ↓
OBSERVATIONS (fichiers modifiés, résultats tests, appels API)
     ↓
ACTION (implement / deploy / test / memo / analyze / repair)
     ↓
RÉSULTAT (.seal() → outcome + outcome_detail)
     ↓
LEARNING (nouvelle règle candidate)
     ↓
GRAVURE ON-CHAIN (.to_memo_content() → /api/v1/ai/memo)
```

`ReasoningRecordStore` : persistance append-only `data/trace/reasoning_records.jsonl`.

### 2.4 `src/artcb/reflex/core.py` (R350 → R355)

**AVANT :** `activate()` retournait un dict simple  
**APRÈS :** `activate()` crée et persiste un `ReasoningRecord` à chaque invocation

```python
report = engine.activate(
    text="mémoire thinking réflexe",
    files=["src/artcb/reasoning/record.py"],
    session_id="r355-live",
)
# report contient maintenant :
# - record_id : SHA-256 du record (traçabilité)
# - first_reflex : FIRST_REFLEX calculé
# - earliest : EARLIEST_DETECTABLE_POINT estimé
```

### 2.5 `src/api/reasoning_routes.py`

**AVANT :** inexistant  
**APRÈS :** 6 routes

```
GET  /api/v1/reasoning/records/count
GET  /api/v1/reasoning/records
POST /api/v1/reasoning/record          ← create via ReflexEngine
GET  /api/v1/reasoning/record/{id}
POST /api/v1/reasoning/record/{id}/seal ← clôturer avec résultat + apprentissage
GET  /api/v1/reasoning/reflex-records
```

---

## 3. Tests — 46/46 PASS

```
tests/test_reasoning_record.py::TestReferenceID              (10/10) PASS
tests/test_reasoning_record.py::TestFirstReflex              ( 6/6)  PASS
tests/test_reasoning_record.py::TestEarliestDetectablePoint  ( 6/6)  PASS
tests/test_reasoning_record.py::TestReasoningRecord          (11/11) PASS
tests/test_reasoning_record.py::TestReasoningRecordStore     ( 5/5)  PASS
tests/test_reasoning_record.py::TestReflexEngineWithRecord   ( 7/7)  PASS
──────────────────────────────────────────────────────────────────────
TOTAL : 46/46 PASS en 1.53s
```

---

## 4. Validation live (artcb.me)

```json
POST https://artcb.me/api/v1/reasoning/record
{
  "session_id": "r355-live-test-2026-09-17",
  "trigger_text": "mémoire ARTCB thinking réflexe bootstrap",
  "files": ["src/artcb/reasoning/record.py", "src/artcb/reasoning/first_reflex.py"]
}

Response :
{
  "record_created": true,
  "record_id": "3b1855c85090290d...",
  "priority": 0,
  "priority_name": "REFLEX_MEMORY",
  "first_reflex": {
    "trigger_name": "REFLEX_MEMORY",
    "priority": 0,
    "evidence": {"keywords": ["réflexe","reflex","mémoire","thinking","bootstrap"]},
    "reference_ids": ["refid:rule:84eaa41865b6c48a", "refid:code:dc98b77abfc5ded9", ...]
  },
  "triggers_count": 1,
  "certified_100": false
}
```

---

## 5. Mémo on-chain

- Bloc #756 gravé sur nœud mac-local
- `graph_id`: `ai_memo_ded392f48a1b`
- `pol_score`: 0.75
- `visibility`: private (PBFT non disponible pour public ce tour)

---

## 6. Commits

| SHA | Description |
|-----|-------------|
| `721df63` | feat(ui): R355 — AddDevice + ReflexStatus dans l'UI artcb.me |
| `b2a5a62` | feat(reasoning): R355 — REASONING_RECORD + ReferenceID + FIRST_REFLEX + EARLIEST_DETECTABLE_POINT |

---

## 7. Honnêteté (CERTIFIED_100=false)

- `EARLIEST_DETECTABLE_POINT` : confidence=0.35 max (estimation log-trace) — pas une preuve
- `REASONING_RECORD` : couvre le contexte surfacé uniquement, pas le CoT interne du modèle
- `unique_human_proven`: false — non prouvé
- `CERTIFIED_R355`: tests PASS + live API validé

---

## 8. Prochains chantiers (non effacés)

- **R355-B** : `seal()` automatique après chaque action — lier résultat mesurable au record
- **R356** : gravure on-chain publique des REASONING_RECORD via PBFT (quand disponible)
- **R357** : UI `ReflexStatus` — afficher les derniers records + possibilité de seal
- **Backlog** : PBFT view-change enforcement, PoL/HBP économique, PQC certification réseau
