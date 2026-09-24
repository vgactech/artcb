# R453 — Tests PBFT view-change + panne nœud (Issues #86 / #88)

**Date :** 2026-09-25  
**SHA commit :** `769f8df296d843decf16df4e804d58706da0be5c`  
**SHA parent :** `f268673` (R432-rapport)  
**Auteur :** agent ARTCB (Bob IDE)  
**Statut :** ✅ DONE — 25/25 tests PASS — Gate DO-178C 124/124 PASS  
**CERTIFIED_100 :** `false`

---

## 1. Contexte

Issues GitHub P0 identifiées lors de l'audit R430 :

| Issue | Titre | État avant R453 |
|-------|-------|----------------|
| **#86** | PBFT public/private + liveness | ❌ Pas de tests dédiés view-change |
| **#88** | PBFT 1 nœud mort + auto-view-change | ❌ Pas de tests panne nœud |

`pbft_view.py` existait déjà (logic VIEW-CHANGE + NEW-VIEW + quorum), mais n'avait aucun test couvrant les scénarios adversariaux critiques : panne primaire, quorum insuffisant, replay, digest altéré, ledger split public/privé.

Correction bonus incluse : `test_r432_fhe_hamming_circuit.py::test_g04_module_version_is_r432` était cassé sur HEAD `f268673` (attendait `"1.1.0"`, module auto-versionné à `"1.1.1"`).

---

## 2. Fichiers modifiés

| Fichier | Action | Avant | Après |
|---------|--------|-------|-------|
| `tests/test_r453_pbft_view_change_node_failure.py` | **NOUVEAU** | absent | 25 tests V01–V25 |
| `tests/test_r432_fhe_hamming_circuit.py` | **CORRIGÉ** | `"1.1.0"` (cassé) | `"1.1.1"` (PASS) |

### Avant (ligne exacte cassée — `tests/test_r432_fhe_hamming_circuit.py:492`)
```python
assert hom.MODULE_VERSION == "1.1.0", (
    f"Attendu 1.1.0, obtenu {hom.MODULE_VERSION}"
)
```

### Après
```python
assert hom.MODULE_VERSION == "1.1.1", (
    f"Attendu 1.1.1, obtenu {hom.MODULE_VERSION}"
)
```

---

## 3. Couverture des 25 tests R453

| Test | Scénario | Résultat |
|------|----------|----------|
| V01 | `primary_of()` déterminisme + rotation modulo N=5 | ✅ PASS |
| V01b | `primary_of(v) == primary_of(v+N)` | ✅ PASS |
| V02 | VIEW-CHANGE émission + vérification cryptographique Ed25519 | ✅ PASS |
| V03 | VIEW-CHANGE rejet si vue non croissante (stale) → `ValueError` | ✅ PASS |
| V04 | VIEW-CHANGE rejet replica absente du registry (binding_enforced=True) | ✅ PASS |
| V05 | Quorum VIEW-CHANGE Q=3 replicas → `quorum_for().ok=True` | ✅ PASS |
| V06 | Quorum insuffisant Q-1=2 replicas → `quorum_for().ok=False` | ✅ PASS |
| V07+V08 | NEW-VIEW émission par nouveau primaire + `verify_new_view=True` | ✅ PASS |
| V09 | NEW-VIEW rejet si `primary` altéré (replay adversarial) | ✅ PASS |
| V10 | NEW-VIEW rejet si `vc_digest` altéré | ✅ PASS |
| V11 | `install_new_view()` avance `view` + `primary` dans le store | ✅ PASS |
| V12 | `install_new_view()` rejet si vue stale | ✅ PASS |
| V13 | **#88** — 1 nœud mort sur 4 → `below_quorum=False` (quorum maintenu) | ✅ PASS |
| V14 | **#88** — 2 nœuds morts sur 4 → `below_quorum=True` | ✅ PASS |
| V15 | `next_reachable_view()` skip vues dont le primaire est injoignable | ✅ PASS |
| V16 | **#86** — `is_public_block()` discrimine blocs publics/privés | ✅ PASS |
| V17 | **#86** — `ensure_split_ledgers()` migration sans perte (2 pub + 1 priv) | ✅ PASS |
| V18 | `accept_view_change()` déduplique les envois du même replica | ✅ PASS |
| V19 | VIEW-CHANGE multi-vues simultanées : isolation correcte | ✅ PASS |
| V20 | Liveness N=3 (1 nœud absent) : quorum maintenu | ✅ PASS |
| V21 | Liveness N=2 (2 nœuds morts) : `below_quorum=True` | ✅ PASS |
| V22 | `snapshot()` expose `processes_stay_up=True` + `not_block_append_bft=True` | ✅ PASS |
| V23 | VIEW-CHANGE signature corrompue → `verify_view_change=False` | ✅ PASS |
| V24 | NEW-VIEW avec `require_pqc=False` (D-032 fenêtre Ed25519) → PASS | ✅ PASS |
| V25 | `view_changes()` filtre lignes JSON invalides | ✅ PASS |

---

## 4. Architecture testée

```
VIEW-CHANGE (replica_id signe)
        │
        ▼
PbftViewStore.accept_view_change()
        │  déduplique par replica_id
        ▼
quorum_for(view)  →  count >= Q=3 ?
        │
        ▼ OUI
emit_new_view()   ←  seul primary_of(view) peut émettre
        │
        ▼
install_new_view()  →  state.view = view, state.primary = primary_of(view)
```

**Paramètres PBFT actifs :**
- N=5 (4 nœuds cloud + Mac) — F=1 — Q=3
- Tolérance 1 panne (issues #86/#88 : 1 nœud mort → quorum maintenu)
- 2 pannes → `below_quorum=True` (observé uniquement, processes_stay_up=True)

**Ledger split (issue #86) :**
- `visibility="public"` OU `pbft_cert` présent → `public/blocks.jsonl`
- sinon → `private/blocks.jsonl`
- Legacy `blocks.jsonl` JAMAIS supprimé

---

## 5. Non-régression

| Suite | Tests | Résultat |
|-------|-------|----------|
| R453 (nouveau) | 25 | ✅ PASS |
| R432 FHE Hamming (corrigé) | 31 | ✅ PASS |
| Gate DO-178C pre-commit | 124 | ✅ PASS |

---

## 6. Fingerprint modules clés

| Module | SHA-256 (16 premiers octets) |
|--------|------------------------------|
| `tests/test_r453_pbft_view_change_node_failure.py` | `6e071408853896e0...` |
| `tests/test_r432_fhe_hamming_circuit.py` | `1456772f658329c0...` |
| `src/artcb/consensus/pbft_view.py` | `1d102255480c42d3...` |
| `src/artcb/consensus/liveness.py` | `d402b0c43b6123b0...` |
| `src/artcb/consensus/replica_identity.py` | `4cc8d2c4d595a65b...` |
| `src/artcb/chain/split_ledger.py` | `4d6dff9d65eb99bc...` |

Artefact complet : `logs/R453_module_fingerprints.json` (git_sha = `769f8df`)

---

## 7. Limites honnêtes

1. **Aucun nœud live n'a été touché** — les tests sont 100% locaux avec des clés de test (`ChainManager` + `install_test_replica_registry()`).
2. **Le gate DO-178C reste FAIL-OPEN localement** (contournable avec `--no-verify`) — R430 préconise une CI GitHub comme autorité finale (chantier ouvert).
3. **Auto-view-change déclenché par timer HTTP** non testé ici (nécessite test d'intégration réseau réel — hors scope R453).
4. **`next_reachable_view()` skippage** testé en monkeypatch `node_registry.pbft_reachable_http_map` — le réseau réel n'est pas consulté.
5. **Issues #86/#88 considérées partiellement adressées** — les tests couvrent la logique pure ; les tests d'intégration live (panne réelle + `artcb.me`) restent dans le backlog.

---

## 8. Prochaines étapes

| Priorité | Chantier |
|----------|----------|
| P0 | Issue #89 — PIN/caméra → WebAuthn natif FAIL-CLOSED |
| P0 | Issue #90 — Bypass internes (capability à usage unique) |
| P0 | Issue #77 — NodeID ↔ clé + TPM/live (9 scénarios adversariaux) |
| P1 | CI GitHub gate DO-178C obligatoire (autorité finale R430) |
| P1 | FORENSIC-02 — Critical Evidence Policy FAIL-CLOSED |
| P1 | TASK-001 biométrie réelle — FAR/FRR/PAD vrais capteurs |

**CERTIFIED_100 reste `false`.**
