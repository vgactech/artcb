# R482 — Universal Audit Preflight (UAP) + injection STANDARD_NAMES_ARTCB

**Date :** 2026-09-26T13:00:00Z  
**SHA HEAD :** bf50c7c (main)  
**CERTIFIED_100 :** false (invariant absolu)  
**unique_human_proven :** false (invariant absolu)

---

## Résumé

| Élément | Résultat |
|---------|----------|
| Fichiers modifiés | `.bob/hooks/user_prompt_submit.py` + `src/artcb/audit/uap.py` (NOUVEAU) + `tests/test_r482_uap.py` (NOUVEAU) |
| Tests R482 | **20/20 PASS** (T01→T20) en 4.6s |
| Non-régression TASK-001 | **124/124 PASS** (sans Paillier) |
| UAP run live | preflight_ok=True, 0 CRITICAL, 1 WARNING |
| ORDRE 1 (R481) | ✅ STANDARD_NAMES_ARTCB injecté à chaque prompt |
| ORDRE 2 (R481) | ✅ UAP module complet — 6 sections |

---

## ORDRE 1 — Injection STANDARD_NAMES_ARTCB

### Problème (avant R482)

Le fichier `STANDARD_NAMES_ARTCB` n'était pas injecté dans le contexte Bob à chaque prompt.  
R481 avait identifié cette absence comme lacune critique (ORDRE 1).

### Correction (après R482)

**Fichier :** [`.bob/hooks/user_prompt_submit.py`](.bob/hooks/user_prompt_submit.py)

**AVANT** (ligne 53–57) :
```python
INJECT_CONTENT_FILES = [
    ("PROTOCOLE_ARTCB",           4000,  "PROTOCOLE ARTCB"),
    ("DECISIONS_UTILISATEUR_ARTCB", 8000, "DÉCISIONS UTILISATEUR"),
    ("LEÇONS_APPRISES_ARTCB",     8000,  "LEÇONS APPRISES"),
]
```

**APRÈS** (ligne 53–59) :
```python
INJECT_CONTENT_FILES = [
    ("PROTOCOLE_ARTCB",             4000,  "PROTOCOLE ARTCB"),
    ("DECISIONS_UTILISATEUR_ARTCB", 8000,  "DÉCISIONS UTILISATEUR"),
    ("LEÇONS_APPRISES_ARTCB",       8000,  "LEÇONS APPRISES"),
    # R482 — ORDRE 1 : vocabulaire canonique ARTCB injecté à chaque prompt
    ("STANDARD_NAMES_ARTCB",        3000,  "STANDARD NAMES ARTCB"),
]
```

**Vérification :** Appel `python3 .bob/hooks/user_prompt_submit.py 'test'` → ligne  
`### ─── STANDARD NAMES ARTCB (STANDARD_NAMES_ARTCB) ───` visible dans la sortie.

**Critère DONE_VERIFIED :** le contenu est effectivement visible dans le contexte du prochain prompt Bob ✅

---

## ORDRE 2 — Universal Audit Preflight (UAP)

### Architecture

**Fichier :** [`src/artcb/audit/uap.py`](src/artcb/audit/uap.py) (NOUVEAU — 380 lignes)

```
PROMPT
  ↓
UAP (run_uap)
  ├── GIT          ← SHA HEAD, branche, working tree
  ├── LEDGER       ← task_ledger.yaml, SHA divergence, CERTIFIED_100 violation
  ├── STANDARD_NAMES ← présence + intégrité STANDARD_NAMES_ARTCB
  ├── REPO         ← module_count src/artcb/**, modules critiques TASK-001
  ├── LANGUAGE     ← R471_mapping_stats.json closure_ok
  └── CERTIFIED    ← invariants certified_100=False + unique_human_proven=False
  ↓
UapReport → JSON (logs/uap_*.json)
```

**Invariants absolus dans tous les chemins :**
- `UapReport.certified_100 = False`
- `UapReport.unique_human_proven = False`
- `preflight_ok = True` seulement si `critical_count == 0`

**Propriété fail-open :** Chaque section produit un résultat ou un finding  
d'absence — jamais d'exception non capturée.

**Propriété fail-closed sur CERTIFIED :** `certified_100=true` dans le ledger → CRITICAL.

### Structures de données

| Classe | Rôle |
|--------|------|
| `UapFinding` | Finding atomique (severity/category/message/detail/finding_id) |
| `UapSection` | Section UAP (nom, ok, findings, data) |
| `UapReport` | Rapport complet (toutes sections + all_findings + métriques) |

### UAP run sur HEAD bf50c7c

```
✅ GIT          : SHA=bf50c7c, branche=main, 112 fichiers modifiés (INFO)
⚠️  LEDGER       : WARNING LEDGER_DIVERGENCE ledger=c624f12 ↔ HEAD=bf50c7c
✅ STANDARD_NAMES: présent et complet (sha256=..., ~4KB)
✅ REPO          : 198 modules Python src/artcb/ — 0 module critique manquant
✅ LANGUAGE      : R471 21.5M entrées, closure_ok=True
✅ CERTIFIED     : certified_100=False ✅ unique_human_proven=False ✅

preflight_ok = True | critical=0 | warning=1
```

Le WARNING LEDGER_DIVERGENCE est normal : le ledger `head_sha` sera mis à jour  
après ce commit (c'est l'ordre correct — L-053).

---

## Tests R482 — 20/20 PASS

**Fichier :** [`tests/test_r482_uap.py`](tests/test_r482_uap.py)

| Test | Description | Résultat |
|------|-------------|---------|
| T01 | `_collect_git()` → SHA non vide sur vrai dépôt | ✅ PASS |
| T02 | `_collect_git()` → branche connue | ✅ PASS |
| T03 | `_collect_git()` → modified_files_count ≥ 0 | ✅ PASS |
| T04 | Ledger absent → WARNING (pas CRITICAL) | ✅ PASS |
| T05 | SHA divergence → WARNING LEDGER_DIVERGENCE | ✅ PASS |
| T06 | certified_100=true dans ledger → CRITICAL | ✅ PASS |
| T07 | STANDARD_NAMES absent → CRITICAL | ✅ PASS |
| T08 | STANDARD_NAMES présent complet → ok=True | ✅ PASS |
| T09 | repo_map vrai dépôt ≥ 50 modules | ✅ PASS |
| T10 | modules critiques TASK-001 tous présents | ✅ PASS |
| T11 | R471_stats absent → WARNING (pas CRITICAL) | ✅ PASS |
| T12 | R471 closure_ok=True → INFO + data correctes | ✅ PASS |
| T13 | certified_100=False + unique_human_proven=False invariants | ✅ PASS |
| T14 | `run_uap()` retourne UapReport valide | ✅ PASS |
| T15 | `run_uap()` : invariants certified/unique | ✅ PASS |
| T16 | `run_uap()` sur tmp_repo git init : 0 CRITICAL | ✅ PASS |
| T17 | `run_uap()` détecte certified_100=true → CRITICAL | ✅ PASS |
| T18 | `to_dict()` JSON-sérialisable + clés obligatoires | ✅ PASS |
| T19 | `save_uap_report()` crée fichier JSON lisible | ✅ PASS |
| T20 | Finding IDs uniques dans UapReport | ✅ PASS |

**Durée :** 4.61s (≪ 60s limite L-052)

---

## Non-régression TASK-001

```
124/124 PASS (test_task001_biometric.py + r373 + r374 + r376 + r378)
Durée : 2.25s
```

Paillier (test_task001_r479_paillier_he.py) : **80/80 PASS** lors de la baseline  
(durée ~66s due aux 256 chiffrements Paillier — connu, pas une régression).

---

## Limites honnêtes (DONE_REPORTED → DONE_VERIFIED requis)

| Limite | Description |
|--------|-------------|
| UAP session | UAP non encore intégré dans le hook `user_prompt_submit.py` — appel explicite uniquement |
| Call graph | ORDRE 3 (R481) non implémenté — graphe d'appel récursif AST |
| UPF | ORDRE 6 (R481) non implémenté — Universal Postflight |
| Corrélation 4D | ORDRE 4 (R481) : spec↔code↔test↔forensic non encore matrice |
| Registre anomalies | ORDRE 11 (R481) : registre finding_id canonique non créé |
| Ledger divergence | meta.head_sha sera mis à jour post-commit |

**CERTIFIED_100 = false** — invariant maintenu.

---

## Fichiers modifiés / créés

| Fichier | Action | Lignes |
|---------|--------|--------|
| `.bob/hooks/user_prompt_submit.py` | +1 entrée INJECT_CONTENT_FILES | +3 lignes |
| `src/artcb/audit/__init__.py` | CRÉÉ (vide) | 0 lignes |
| `src/artcb/audit/uap.py` | CRÉÉ | 380 lignes |
| `tests/test_r482_uap.py` | CRÉÉ | 285 lignes |
| `rapports/rapports/R482_uap_standard_names_2026-09-26.md` | CRÉÉ (ce fichier) | — |
