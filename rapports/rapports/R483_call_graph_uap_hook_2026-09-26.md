# R483 — Graphe d'appel AST récursif (ORDRE 3) + UAP branché automatiquement

**Date :** 2026-09-26T14:00:00Z  
**SHA HEAD avant commit :** ef6cfd6 (main)  
**CERTIFIED_100 :** false (invariant absolu)  
**unique_human_proven :** false (invariant absolu)

---

## Résumé

| Élément | Résultat |
|---------|----------|
| Fichiers créés/modifiés | `call_graph.py` (NOUVEAU) + `test_r483_call_graph.py` (NOUVEAU) + `user_prompt_submit.py` (MODIFIÉ) |
| Tests R483 | **21/21 PASS** (T01→T21) en 1.5s |
| Non-régression totale | **139/139 PASS** (21+20+98) |
| ORDRE 3 R481 | ✅ Graphe d'appel AST récursif complet |
| UAP automatique | ✅ Branché dans le hook `user_prompt_submit.py` |

---

## ORDRE 3 — Graphe d'appel AST récursif

### Fichier créé

[`src/artcb/audit/call_graph.py`](src/artcb/audit/call_graph.py) — 430 lignes

### Architecture

```
repository
 ↓ scan_module() : ast.parse par fichier
package → module → classe → fonction
 ↓ _collect_calls_in_body() : ast.NodeVisitor
CallSite (caller_module, caller_func, callee_name, line, args_count)
 ↓ build_call_graph() : graphe d'adjacence
dict edges : caller_qname → [callee_names]
 ↓ get_transitive_callees() : DFS récursif
CallChain (chain, has_cycle, depth)
 ↓ get_impact_of_change() : BFS complet (ORDRE 12)
[fonctions transitivement impactées]
```

### Structures de données

| Classe | Rôle |
|--------|------|
| `CallSite` | Appel détecté (module, fonction appelante, callee, ligne, nb args) |
| `FunctionNode` | Nœud du graphe (module_path, qualified_name, lineno, call_sites) |
| `CallChain` | Chaîne A→B→…→feuille (avec détection cycle) |
| `CallGraphReport` | Rapport complet (nodes, edges, cycles, unreachable, scan_errors) |

### Propriétés

- **Toute fonction transitivement appelée** par une fonction modifiée entre dans le périmètre d'audit (ORDRE 3 §2).
- **Détection de cycles** : DFS avec `in_stack` — cycle → `has_cycle=True` dans la chaîne, stop.
- **Fail-open** : erreur AST sur un fichier → `scan_errors` (warning), pas crash.
- **Nœuds sans prédécesseur** : exposés dans `unreachable` (fonctions non appelées dans la scope analysée).
- **Résolution locale** : appels non résolus → `[external]::callee` (stdlib/externe non analysé).

### Résultats sur src/artcb

```
nodes         : ~198 fonctions
edges         : ~87 fonctions avec arêtes
scan_errors   : 0
cycles        : variable (dépend des modules importés dynamiquement)
```

### Fonctions critiques TASK-001 trouvées (T21)

`check_uniqueness`, `fuzzy_extract`, `fuzzy_reproduce`, `hamming_distance_bits`, `enroll_biometric` — toutes présentes dans le graphe.

---

## UAP branché automatiquement dans le hook

### AVANT (`.bob/hooks/user_prompt_submit.py` ligne 388-394)

```python
# R371 — Injection contenu réel des fichiers de règles
try:
    rc = inject_rules_content()
    ...
print("\n".join(lines))
return 0
```

### APRÈS (lignes 396-418)

```python
# R483 — UAP automatique : résumé compact en fin de contexte
try:
    import sys as _sys
    if str(ROOT) not in _sys.path:
        _sys.path.insert(0, str(ROOT))
    from src.artcb.audit.uap import run_uap
    _uap = run_uap(ROOT)
    _uap_status = "✅ PASS" if _uap.preflight_ok else f"⚠ {_uap.critical_count} CRITICAL"
    lines.append(f"## UAP R483 — preflight_ok={_uap.preflight_ok} {_uap_status}...")
    lines.append(f"   git={_uap.git_sha} | certified_100=false | unique_human_proven=false")
    for f in _uap.all_findings:
        if f.severity == "CRITICAL":
            lines.append(f"   🔴 CRITICAL [{f.category}] {f.message}")
except Exception as _uap_exc:
    lines.append(f"## UAP R483 — fail-open (erreur: {type(_uap_exc).__name__})")
```

**Propriété :** Fail-open total — si UAP échoue, une ligne d'erreur est injectée mais le hook continue.

---

## Tests R483 — 21/21 PASS

**Fichier :** [`tests/test_r483_call_graph.py`](tests/test_r483_call_graph.py)

| Test | Description | Résultat |
|------|-------------|---------|
| T01 | `scan_module()` extrait fonctions top-level + méthodes | ✅ |
| T02 | `scan_module()` extrait les sites d'appel foo→bar | ✅ |
| T03 | `scan_module()` sur syntaxe invalide → error (fail-open) | ✅ |
| T04 | `build_call_graph()` trouve les nœuds des deux modules | ✅ |
| T05 | `build_call_graph()` construit arêtes entry_point→process | ✅ |
| T06 | Invariants certified_100=False + unique_human_proven=False | ✅ |
| T07 | `get_transitive_callees()` retourne chaîne complète | ✅ |
| T08 | Fonction inconnue → [] | ✅ |
| T09 | max_depth=1 tronque la traversée | ✅ |
| T10 | `get_impact_of_change()` inclut callees directs | ✅ |
| T11 | `get_impact_of_change()` inclut callees transitifs | ✅ |
| T12 | Fonction sans arêtes → juste elle-même | ✅ |
| T13 | Cycle alpha→beta→alpha détecté | ✅ |
| T14 | Chaîne cyclique marquée `has_cycle=True` | ✅ |
| T15 | Pas de faux cycle dans graphe acyclique | ✅ |
| T16 | `CallGraphReport` expose tous les champs attendus | ✅ |
| T17 | Chaque `FunctionNode` a `module_path` et `lineno` valides | ✅ |
| T18 | `MODULE_VERSION` est une chaîne non vide | ✅ |
| T19 | Hook `user_prompt_submit.py` produit ligne `UAP R483` | ✅ |
| T20 | Ligne UAP contient `certified_100=false` | ✅ |
| T21 | Fonctions critiques TASK-001 trouvées dans le graphe | ✅ |

**Durée :** 1.5s (≪ 60s limite L-052)

---

## Non-régression

```
21/21 (R483) + 20/20 (R482 UAP) + 98/98 (TASK-001 sans Paillier) = 139/139 PASS
Durée : 9.3s
Gate DO-178C : PASS (hook pre-commit)
```

---

## Limites honnêtes

| Limite | Description |
|--------|-------------|
| Résolution noms | Import dynamique (`import_module`, `__import__`) non résolu statiquement |
| Résolution croisée | Arêtes inter-modules basées sur le nom simple (peut manquer des qualifiés) |
| ORDRE 6 UPF | Universal Postflight non encore implémenté |
| ORDRE 11 registre | Registre anomalies canonique non encore créé |

**CERTIFIED_100 = false** — invariant maintenu.

---

## Fichiers modifiés / créés

| Fichier | Action |
|---------|--------|
| `src/artcb/audit/call_graph.py` | CRÉÉ (430 lignes) |
| `tests/test_r483_call_graph.py` | CRÉÉ (260 lignes) |
| `.bob/hooks/user_prompt_submit.py` | +14 lignes (UAP auto + sys.path fix) |
| `rapports/rapports/R483_call_graph_uap_hook_2026-09-26.md` | CRÉÉ |
