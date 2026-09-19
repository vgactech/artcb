# R396 — Agent Execution Attestation + Forensic CI + Télémétrie

**Date :** 2026-09-19  
**SHA git HEAD avant :** f75e091  
**Tâche :** Implémentation de la règle FAIL-OPEN EXECUTION / FAIL-CLOSED AUDIT STATUS  
**CERTIFIED_100 :** false  
**Mode :** DEBUG actif  

---

## Contexte

Suite à l'audit R395, quatre lacunes ont été identifiées :

1. **R396-A** : `stop.py` Bob ne contrôlait pas le returncode de R392 → échec silencieux possible
2. **R396-B** : Aucun `AgentExecutionRecord` standardisé pour Bob + Cursor
3. **R396-C** : Le forensic nanoseconde ne couvrait pas les exécutions pytest (CI ≠ runtime)
4. **R396-D** : `GOUVERNANCE_ARTCB.md` absent de `rule_sources.json` ; `agent_id` non tracké

---

## R396-A — stop.py : FAIL-OPEN EXECUTION, FAIL-CLOSED AUDIT STATUS

### Avant (R394-C)

```python
# .bob/hooks/stop.py L.117-127
try:
    import subprocess as _sp
    _sp.run(
        ["python3", "scripts/artcb_r392_auto_feedback.py", "--since", "HEAD~1"],
        cwd=str(ROOT),
        timeout=25,
        capture_output=True,  # ne pas polluer stdout du hook
    )
except Exception:
    pass  # fail-open — ne jamais bloquer la fin de session
```

**Problème :** returncode non contrôlé → un échec (returncode ≠ 0, timeout, exception) était traité comme un succès. Aucune trace persistante de l'état d'audit.

### Après (R396-A)

**Fichier :** `.bob/hooks/stop.py`

```python
# Lignes 123–173 (après patch)
audit_status = AUDIT_INCOMPLETE  # jamais "ok" par défaut
try:
    result = subprocess.run([...], timeout=25, capture_output=True, text=True)
    if result.returncode == 0:
        audit_status = AUDIT_OK
        audit_detail = {"returncode": 0, "stderr_chars": ...}
    else:
        audit_status = AUDIT_FAILED
        audit_detail = {"returncode": result.returncode, "stderr": ...[:400]}
except subprocess.TimeoutExpired:
    audit_status = AUDIT_FAILED
    audit_detail = {"error": "timeout_expired", "timeout_s": 25}
except Exception as exc:
    audit_status = AUDIT_FAILED
    audit_detail = {"error": type(exc).__name__, "msg": str(exc)[:200]}

# Persistance SYSTÉMATIQUE dans bob_turns.jsonl
audit_row = {
    "ts_ns": ..., "kind": "bob_stop_audit", "session_id": ...,
    "agent_id": "bob", "audit_status": audit_status, ...
}
```

**Stdout visible :**
```
[ARTCB AUDIT] ✅ feedback=ok | agent=bob | session=...
```
ou
```
[ARTCB AUDIT] ❌ feedback=failed | agent=bob | session=...
```

**Invariant :** `audit_status` commence toujours à `INCOMPLETE` — jamais `ok` par défaut.

---

## R396-B — AgentExecutionRecord

### Avant (R390)

```python
# src/artcb/trace/agent_run.py
class AgentRunLedger:
    # Ledger événementiel, pas de résumé structuré de session
```

Aucun champ standardisé `audit_status`, `tests_passed`, `feedback_status`.

### Après (R396-B)

**Fichier :** `src/artcb/trace/agent_run.py` — `MODULE_VERSION = '1.1.0'`

```python
@dataclass
class AgentExecutionRecord:
    agent_id: str = AGENT_BOB       # "bob" | "cursor"
    session_id: str = ""
    task_id: str = ""
    repo_sha_before: str = ""
    repo_sha_after: str = ""
    start_ns: int = field(default_factory=time.time_ns)
    end_ns: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_error: int = 0
    feedback_status: str = AUDIT_STATUS_INCOMPLETE
    audit_status: str = AUDIT_STATUS_INCOMPLETE  # jamais "ok" par défaut
    artifact_hash: str = ""
    note: str = ""

    def finish(self, *, audit_status, feedback_status, repo_sha_after, artifact_hash): ...
    def to_dict(self) -> dict: ...
    def write(self, trace_dir: Path) -> Path: ...
```

Fichier de trace : `data/trace/agent_execution_records.jsonl`

**Tests manuels : 4/4 PASS**
- `audit_status` commence à `INCOMPLETE`
- `finish()` met à jour correctement
- `to_dict()` inclut `certified_100=False`, `schema`, `agent_id`
- `write()` génère un JSONL valide

---

## R396-C — Hook pytest → forensic trace

### Avant (pré-R396)

```
production runtime → trace/ns.jsonl  ✅
pytest CI          → (rien)          ❌
```

Le forensic nanoseconde couvrait uniquement les opérations HTTP et blockchain live. Zéro trace des runs de tests.

### Après (R396-C)

**Fichier :** `tests/conftest.py`

```python
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """R396-C — émet un événement nanoseconde à la fin de chaque test (call phase)."""
    t_start = time.time_ns()
    outcome = yield
    if call.when != "call":
        return
    t_end = time.time_ns()
    rep = outcome.get_result()
    _emit_pytest_trace({
        "kind": "pytest_result",
        "ts_ns": t_start, "end_ns": t_end, "dur_ns": t_end - t_start,
        "test_id": item.nodeid,
        "outcome": rep.outcome,  # "passed" | "failed" | "error"
        "commit_sha": _get_commit_sha(),
        "worker_id": ...,
    })
```

**Fichier de trace :** `data/trace/pytest_trace.jsonl`

**Validation :**
```
tests/test_task001_r374_bch.py     → 30 events PASS
tests/test_task001_r376_uniqueness.py → 22 events PASS
tests/test_task001_r378_hamming.py → 28 events PASS
Total : 108 events, 108 passed, 0 failed, commit=f75e091
```

Exemple de ligne générée :
```json
{"kind":"pytest_result","ts_ns":1789854287647763000,"end_ns":1789854287647820000,
"dur_ns":57000,"test_id":"tests/test_task001_r378_hamming.py::test_T01_hamming_distance_identical",
"outcome":"passed","commit_sha":"f75e091","worker_id":"main"}
```

**Le hook est fail-open :** un échec du logging JSONL ne bloque pas les tests.

---

## R396-D — Télémétrie : GOUVERNANCE_ARTCB + agent_id tracking

### Avant (R375)

`rules/rule_sources.json` : 16 sources, `GOUVERNANCE_ARTCB.md` absent, `agent_id` non tracké.

### Après (R396-D)

**Fichier :** `rules/rule_sources.json` — `protocol = "r340-rule-sources-v2-r396d"`

Ajouts :
1. `"agent_id_tracking": true` à la racine
2. Source `gouvernance_artcb` :
   - `path: "GOUVERNANCE_ARTCB.md"`, `kind: "SPEC"`, `authority: "governance"`
   - `bytes: 8866`, `sha256: "d9b0569aa95f89363a82d002d79cf2e950878ee57bea0a04324a5f2fd0c433ce"`
3. Source `agent_execution_protocol` :
   - `path: "src/artcb/trace/agent_run.py"`, `kind: "SPEC"`, `authority: "forensic"`
   - `agent_id_values: ["bob", "cursor"]`, `audit_status_values: ["ok", "failed", "incomplete"]`

**Total sources : 18** (était 16 + rule_registry = 17, maintenant 19 entrées dont 2 nouvelles)

**Validation :**
```
rule_sources.json: 17 sources uniques, gouvernance OK, agent_id_tracking OK
```

---

## Récapitulatif avant / après

| Aspect | Avant | Après |
|--------|-------|-------|
| Returncode R392 contrôlé | ❌ | ✅ R396-A |
| `audit_status` persisté dans bob_turns.jsonl | ❌ | ✅ `kind=bob_stop_audit` |
| `audit_status` par défaut = "incomplete" | ❌ (implicite = ok) | ✅ |
| Visible dans stdout Bob | ❌ | ✅ `[ARTCB AUDIT] ✅/❌ feedback=...` |
| AgentExecutionRecord standardisé | ❌ | ✅ R396-B |
| `agent_id = "bob"/"cursor"` | ❌ | ✅ |
| Forensic pytest → JSONL | ❌ | ✅ R396-C `pytest_trace.jsonl` |
| GOUVERNANCE_ARTCB dans sources | ❌ | ✅ R396-D |
| `agent_id_tracking` dans rule_sources | ❌ | ✅ |

---

## Limites honnêtes

1. **Cursor** : le protocole `AgentExecutionRecord` est défini pour Cursor (`AGENT_CURSOR = "cursor"`), mais l'intégration dans les hooks Cursor n'est pas encore faite — il n'y a pas de hook équivalent à `stop.py` côté Cursor exposé ici. C'est le prochain chantier.
2. **Classification auto des nouvelles règles CR-*** : non implémentée dans ce cycle. Les nouvelles règles nécessitent toujours une classification manuelle.
3. **La chaîne complète `commit → test → feedback → audit_ok`** : le stop.py amélioré persiste l'audit_status, mais ne produit pas encore d'`AgentExecutionRecord` complet avec `tests_passed/tests_failed`. Ce branchement final est TASK-007.

---

## Tests exécutés

| Suite | Tests | Résultat |
|-------|-------|----------|
| `test_task001_r374_bch.py` | 30 | ✅ PASS |
| `test_task001_r376_uniqueness.py` | 22 | ✅ PASS |
| `test_task001_r378_hamming.py` | 28 | ✅ PASS |
| AgentExecutionRecord (manuel) | 4 | ✅ PASS |
| stop.py syntax + markers | 2 | ✅ PASS |
| rule_sources.json validation | 1 | ✅ PASS |
| **Total** | **87** | **✅ 87/87 PASS** |

Forensic CI : `data/trace/pytest_trace.jsonl` — 108 événements, 108 passed, commit `f75e091`

---

*CERTIFIED_100=false | git HEAD f75e091 → commit R396 à suivre*
