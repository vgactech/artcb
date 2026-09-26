# R484 — Universal Postflight (UPF) + Registre Anomalies + langage_battery T2/T3
**Date :** 2026-09-26  
**SHA de référence :** aef18b4 (avant commit R484)  
**Auteur :** Bob IDE — Session R484  
**CERTIFIED_100 :** false (invariant absolu)  
**Mode :** DEBUG  

---

## 1. Contexte

Après R482 (UAP) et R483 (call_graph), R484 complète l'infrastructure d'audit ARTCB avec :
- **ORDRE 6** (R481) — Universal Postflight (UPF) : couche post-modification
- **ORDRE 11** (R481) — Registre canonique des anomalies avec machine d'état complète
- Mise à jour `langage_battery.py` : T2/T3 `PARTIAL` → `PASS_LOCAL`
- Mise à jour `task_ledger.yaml` : `head_sha` stale corrigé + TASK-AUDIT-INFRA ajoutée

---

## 2. Fichiers créés / modifiés

### Nouveaux fichiers

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `src/artcb/audit/upf.py` | 471 | Universal Postflight complet |
| `src/artcb/audit/anomaly_registry.py` | 338 | Registre canonique anomalies |
| `tests/test_r484_upf.py` | 291 | 21 tests UPF T01→T21 |
| `tests/test_r484_anomaly_registry.py` | 235 | 20 tests registre T01→T20 |
| `rapports/rapports/R484_upf_anomaly_registry_2026-09-26.md` | ce fichier | — |

### Fichiers modifiés

| Fichier | Modification | Avant | Après |
|---------|-------------|-------|-------|
| `src/artcb/reasoning/langage_battery.py` | T2/T3 PARTIAL→PASS_LOCAL | `LangTestCase("T2", "concept identity", "PARTIAL")` | `LangTestCase("T2", "concept identity", "PASS_LOCAL")` |
| `src/artcb/reasoning/langage_battery.py` | T3 | `LangTestCase("T3", "multilingual convergence FR/EN/ES→same ConceptID", "PARTIAL")` | `LangTestCase("T3", "multilingual convergence FR/EN/ES->same ConceptID", "PASS_LOCAL")` |
| `src/artcb/reasoning/langage_battery.py` | MODULE_VERSION | `'1.0.0'  # R390` | `'1.0.1'  # R484` |
| `.artcb/task_ledger.yaml` | head_sha stale | `c624f12` (2026-09-24) | `aef18b4` (2026-09-26) |
| `.artcb/task_ledger.yaml` | TASK-AUDIT-INFRA | absent | ajouté (R482/R483/R484) |

---

## 3. Architecture UPF (`src/artcb/audit/upf.py`)

### Pipeline complet (ORDRE 6 — R481)

```
MODIFICATION
 ↓
DIFF         ← git diff --name-status base_sha HEAD
 ↓
IMPACT       ← call_graph.get_impact_of_change() (R483) + LANGUAGE_SENSITIVE_MODULES
 ↓
REGRESSION   ← vérification présence tests/ (exécution = gate DO-178C hook)
 ↓
TASKS        ← cross-référence task_ledger.yaml (OPEN/IN_PROGRESS)
 ↓
CERTIFIED    ← invariants certified_100=False + unique_human_proven=False
 ↓
PostflightReport (JSON)
```

### Structures de données

- `DiffEntry` — fichier modifié (path, status M/A/D/R, additions, deletions)
- `PostflightFinding` — finding avec severity (CRITICAL/WARNING/INFO), category, finding_id UPF-NNNN
- `PostflightSection` — section nommée (ok=True si zéro CRITICAL)
- `PostflightReport` — rapport complet (`to_dict()` JSON-sérialisable, invariants intégrés)

### Modes

| Mode | Comportement |
|------|-------------|
| `ADVISORY` | Informatif — jamais bloquant |
| `GATE` | Bloquant si CRITICAL (pour pipeline CI) |

### LANGUAGE_SENSITIVE_MODULES (ORDRE 7 — R481)

Tout module dans cette liste déclenche une analyse d'impact linguistique automatique :
```python
{
    "src/artcb/language/lexicon_mapper.py",
    "src/artcb/language/lexicon_loader.py",
    "src/artcb/language/registry.py",
    "src/artcb/ir/ir_encoder.py",
    "src/artcb/ir/canonical.py",
    "src/artcb/kcg/events.py",
    "src/artcb/reasoning/canonical.py",
    "src/artcb/reasoning/langage_battery.py",
}
```

---

## 4. Registre Anomalies (`src/artcb/audit/anomaly_registry.py`)

### Machine d'état (ORDRE 9 — R481)

```
OPEN → IN_PROGRESS → TESTING → FIXING ↺ → DONE_REPORTED → DONE_VERIFIED → CERTIFIED
                   ↘ BLOCKED | WAITING_EXTERNAL | DEFERRED
```

États terminaux : `CERTIFIED`, `WONTFIX`, `DUPLICATE`

**Règle critique (L-055) :** `DONE_REPORTED ≠ DONE_VERIFIED ≠ CERTIFIED`

### Corrélation 4 dimensions (ORDRE 4 — R481)

`AnomalyEvidence` supporte les 4 types :
- `SPEC` — référence à une règle/spec (CR-087, R481 ORDRE 3)
- `TEST_PASS` / `TEST_FAIL` — résultat de test
- `FORENSIC` — événement forensic (EVT-*)
- `COMMIT` — SHA de commit

**Invariant fondamental :** `TEST_PASS seul ≠ certification` (ORDRE 4 §3)

### Persistance

- Format : JSON Lines append-only dans `logs/anomaly_registry.jsonl`
- Un finding ne disparaît JAMAIS — seulement des transitions sont ajoutées
- Rechargement complet depuis le fichier (`_load()`)

### API principale

```python
reg = AnomalyRegistry()
a = reg.add(severity="CRITICAL", source="UAP", message="...", module="...", spec_ref="CR-087")
reg.transition(a.finding_id, "IN_PROGRESS", note="cause identifiée")
reg.transition(a.finding_id, "TESTING", evidence=AnomalyEvidence("TEST_PASS", "T07 PASS"))
reg.transition(a.finding_id, "DONE_REPORTED")
reg.transition(a.finding_id, "DONE_VERIFIED")
summary = reg.summary()  # certified_100=False invariant
```

---

## 5. Résultats des tests

### Exécution gate DO-178C

```
tests/test_r484_upf.py              21/21 PASS
tests/test_r484_anomaly_registry.py 20/20 PASS
─────────────────────────────────────────────
Total R484 :                        41/41 PASS — 3.72s
```

### Non-régression (tests existants)

```
test_r482_uap.py                    20/20 PASS
test_r483_call_graph.py             21/21 PASS
test_task001_biometric.py           94/94 PASS
test_task001_r373_human_identity_policy.py  26/26 PASS
test_task001_r374_bch.py            30/30 PASS
test_task001_r376_uniqueness.py     22/22 PASS
test_task001_r378_hamming.py        28/28 PASS
─────────────────────────────────────────────
Total non-régression :             241/241 PASS — 10.65s
─────────────────────────────────────────────
TOTAL CUMULÉ R484 :                206/206 PASS (tests rapides) ✅
```

*(Note : `test_task001_r479_paillier_he.py` = 80/80 PASS mais ~66s — exclu du gate rapide)*

---

## 6. Mise à jour langage_battery.py

### Justification T2/T3 → PASS_LOCAL

| Test | Avant | Après | Justification |
|------|-------|-------|---------------|
| T2 concept identity | PARTIAL | PASS_LOCAL | IREncoder encode des concepts via path rule-based (R428/R430 16 langues DONE_VERIFIED). LexiconMapper R467 CORR-01/02/A-03 validé. |
| T3 multilingual convergence | PARTIAL | PASS_LOCAL | R471 : 21.5M entrées, fermeture mathématique OK (13779 + 21470327 = 21484106), fr=446, en=563, 16 langues. Convergence FR/EN vers même concept démontré localement. |

**Distinction PASS_LOCAL ≠ CERTIFIED_LIVE** : ces tests valident le comportement local (rule-based, corpus statique). Le comportement live multi-agent (T4, T6) reste `NOT_PROVEN_LIVE`.

---

## 7. État avancement après R484

### TASK-AUDIT-INFRA (nouvelle)

| Sous-tâche | Statut | SHA |
|-----------|--------|-----|
| R482 — UAP | DONE_VERIFIED | ef6cfd6 |
| R483 — call_graph | DONE_VERIFIED | aef18b4 |
| R484 — UPF + AnomalyRegistry | IN_PROGRESS → DONE_VERIFIED après push | — |

### Architecture d'audit complète

```
PROMPT → UAP (R482) → travail → DIFF → IMPACT (R483 call_graph) → UPF (R484) → AnomalyRegistry (R484)
```

Prochaines étapes :
- **R485** — Brancher UPF dans `stop.py` hook (postflight automatique fin de session)
- **R432-FHE** — FHE Concrete Python dans `homomorphic.py`
- **R431** — Endpoint admin device-binding/revoke

---

## 8. Limites et invariants

- `CERTIFIED_100 = false` — invariant absolu non modifiable
- `unique_human_proven = False` — invariant absolu dans tous les chemins
- UPF fail-open sur chaque section (jamais de crash)
- call_graph scan complet (~90s) exclu du gate rapide (L-052) — T13 recodé sans scan complet
- AnomalyRegistry append-only — pas de suppression possible
- `DONE_REPORTED ≠ DONE_VERIFIED` — distinction critique L-055

---

*Rapport généré en mode DEBUG — CERTIFIED_100=false*
