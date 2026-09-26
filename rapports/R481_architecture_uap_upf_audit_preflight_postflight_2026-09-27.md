# R481 — Architecture UAP/UPF : Universal Audit Preflight + Universal Postflight pour Bob ARTCB

**Date :** 2026-09-27  
**Auteur :** Agent Bob IDE — rapport architectural sur demande explicite  
**SHA HEAD :** `be42d0d`  
**CERTIFIED_100 :** `false` — invariant absolu  
**Nature :** Rapport de conception uniquement — aucune modification de code dans ce rapport  
**Rapport précédent lié :** R464 (injection `STANDARD_NAMES_ARTCB` manquante), R375 (corpus telemetry), R394 (fingerprint chain)

---

## Préambule honnête

Ce rapport décrit une **architecture cible** et non un état accompli. Conformément au PROTOCOLE ARTCB, les affirmations ci-dessous sont distinguées entre :

- ✅ **EXISTANT** : implémenté, vérifié sur `be42d0d`
- ⚠️ **PARTIEL** : existant mais incomplet ou fail-open
- ❌ **MANQUANT** : non implémenté à ce jour

L'analyse est fondée sur la lecture directe du dépôt (`be42d0d`), pas sur des suppositions.

---

## 1. État factuel du mécanisme actuel (be42d0d)

### 1.1 Ce qui est réellement automatique

**Hook `user_prompt_submit.py`** — lu ligne par ligne :

```python
INJECT_CONTENT_FILES = [
    ("PROTOCOLE_ARTCB",             4000,  "PROTOCOLE ARTCB"),
    ("DECISIONS_UTILISATEUR_ARTCB", 8000,  "DÉCISIONS UTILISATEUR"),
    ("LEÇONS_APPRISES_ARTCB",       8000,  "LEÇONS APPRISES"),
]
AUTO_PROMPT_TAIL_CHARS = 6000
```

| Mécanisme | État |
|---|---|
| Injection PROTOCOLE_ARTCB | ✅ automatique à chaque prompt |
| Injection DECISIONS_UTILISATEUR_ARTCB | ✅ automatique |
| Injection LEÇONS_APPRISES_ARTCB | ✅ automatique |
| Injection AUTO_PROMPT_ARTCB (6000 chars fin) | ✅ automatique |
| Injection STANDARD_NAMES_ARTCB | ❌ **absent de INJECT_CONTENT_FILES** (R464 le constatait déjà) |
| Détection divergence git SHA | ✅ automatique |
| Chargement task_ledger | ✅ automatique |
| Continuité de session | ✅ automatique |
| Prochaine action injectée | ✅ automatique |
| Mots-clés priorité réflexe | ✅ 14 domaines détectés |
| Forensic Ledger (`src/artcb/trace/forensic.py`) | ✅ existant — 34 584 octets |
| DO-178C gate pytest avant commit | ✅ hook `post_commit` — 124 tests |

### 1.2 Ce qui est partiel ou fail-open

| Mécanisme | État | Preuve |
|---|---|---|
| Forensic criticité | ⚠️ fail-open | R452 — politique criticité non terminée |
| Analyse graphe d'appel récursif | ❌ absent | Aucun script `call_graph_*.py` dans `/scripts` |
| Corrélation code ↔ test ↔ forensic ↔ spec | ❌ absent | Pas de script de croisement |
| Injection STANDARD_NAMES_ARTCB | ❌ absent | Confirmé sur HEAD `be42d0d` |
| Couverture linguistique automatique toutes tâches | ⚠️ manuel | R471 — `CERTIFIED_100=false` |
| Postflight diff de régression cross-domaine | ❌ absent | Pas de script post-commit |
| Blocage automatique sur anomalie forensic | ❌ absent | fail-open documenté |

### 1.3 Inventaire infrastructure existante réutilisable

Le dépôt contient déjà les briques suivantes — **à ne pas recréer** :

| Fichier / Module | Rôle | Réutilisation UAP |
|---|---|---|
| `.bob/hooks/user_prompt_submit.py` | Injection contexte à chaque prompt | Étendre `INJECT_CONTENT_FILES` |
| `.bob/hooks/stop.py` | Fin de session | Étendre avec postflight SHA |
| `.bob/hooks/post_tool_use.py` | Après chaque outil | Hooks postflight outil |
| `src/artcb/trace/forensic.py` | ForensicLedger JSONL hash-chain | Lecture post-correction |
| `src/artcb/trace/agent_run.py` | Enregistrement runs agent | Baseline régression |
| `rules/rule_corpus_index.json` | 230 CR-* — corpus normatif | Vérification couverture |
| `rules/rule_registry.json` | 20 RT-* — règles opérationnelles | Gate preflight |
| `rules/rule_coverage.json` | 148 marqueurs couverture | Diff coverage |
| `rules/task_ledger.yaml` | Tâches OPEN/IN_PROGRESS | Chargé à chaque prompt |
| `scripts/artcb_r394_module_fingerprints.py` | Fingerprint SHA modules | Baseline module |
| `scripts/artcb_r375_corpus_refresh.py` | Scanner corpus 230 CR-* | Reuse dans UAP scanner |
| `data/trace/bob_turns.jsonl` | Traces turns Bob | Historique runs |
| `logs/R471_mapping_stats.json` | Stats 21.5M entrées / 16 langues | Baseline langue |
| `STANDARD_NAMES_ARTCB` | Registre canonique des noms | À injecter |

---

## 2. Architecture cible UAP — Universal Audit Preflight

### 2.1 Principe

Le UAP est un **module Python exécuté automatiquement par `user_prompt_submit.py`** avant l'injection du prompt dans le modèle. Il ne remplace pas le modèle — il enrichit le contexte de manière déterministe et traçable.

Le modèle reste le **moteur de raisonnement**. Le UAP est la **couche de preuve indépendante du modèle**.

```
Prompt utilisateur
        ↓
user_prompt_submit.py
        ↓
┌─────────────────────────────────┐
│  UAP — Universal Audit Preflight│
│                                 │
│  1. SHA Git réel                │
│  2. Task Ledger                 │
│  3. Session Continuation        │
│  4. STANDARD_NAMES_ARTCB (fix)  │
│  5. Repository Map (modules)    │
│  6. Open Findings (anomalies)   │
│  7. Language Matrix (baseline)  │
│  8. Regression Baseline (SHA)   │
└─────────────────────────────────┘
        ↓
Contexte enrichi → Modèle
```

### 2.2 Composants UAP — fichiers à créer

#### `scripts/artcb_r481_uap_preflight.py`

**Responsabilité :** Calcule le contexte UAP et retourne un bloc JSON/texte injectables.

**Fonctions (à créer, pas de duplication) :**

| Fonction | Entrée | Sortie | Dépendance existante |
|---|---|---|---|
| `get_git_sha()` | — | `str` SHA HEAD | Aucune (subprocess git) |
| `load_task_ledger(path)` | chemin yaml | dict tâches OPEN/IN_PROGRESS | `rules/task_ledger.yaml` |
| `scan_open_findings(forensic_path)` | chemin JSONL | liste anomalies non résolues | `src/artcb/trace/forensic.py` |
| `load_language_baseline(stats_path)` | chemin JSON | dict lang→count | `logs/R471_mapping_stats.json` |
| `compute_module_map(src_root)` | chemin src | dict module→fonctions (shallow) | Python `ast` stdlib |
| `check_standard_names_loaded(content_files)` | liste fichiers injectés | bool + warning | `.bob/hooks/user_prompt_submit.py` |
| `build_uap_block(...)` | tous les résultats | str bloc texte injectable | — |

**⚠️ Ne pas recréer :**
- Ne pas réécrire `ForensicLedger` — le lire seulement
- Ne pas réécrire `task_ledger.yaml` — le parser seulement
- Ne pas réécrire le scanner R375 — l'importer si possible

#### Fix immédiat dans `user_prompt_submit.py` (ligne ~4)

```python
# AVANT :
INJECT_CONTENT_FILES = [
    ("PROTOCOLE_ARTCB",             4000,  "PROTOCOLE ARTCB"),
    ("DECISIONS_UTILISATEUR_ARTCB", 8000,  "DÉCISIONS UTILISATEUR"),
    ("LEÇONS_APPRISES_ARTCB",       8000,  "LEÇONS APPRISES"),
]

# APRÈS :
INJECT_CONTENT_FILES = [
    ("PROTOCOLE_ARTCB",             4000,  "PROTOCOLE ARTCB"),
    ("DECISIONS_UTILISATEUR_ARTCB", 8000,  "DÉCISIONS UTILISATEUR"),
    ("LEÇONS_APPRISES_ARTCB",       8000,  "LEÇONS APPRISES"),
    ("STANDARD_NAMES_ARTCB",        3000,  "STANDARD NAMES"),   # R481 — fix R464
]
```

C'est **le seul changement de code obligatoire à court terme**. Une ligne. Pas de refactoring.

---

## 3. Architecture cible UPF — Universal Postflight

### 3.1 Principe

Le UPF s'exécute **après chaque modification substantielle** (détecté par un changement dans le working tree git). Il vérifie la cohérence entre le code modifié et les quatre axes : code, tests, forensic, spécification.

```
Modification code
        ↓
git diff --stat (fichiers modifiés)
        ↓
┌──────────────────────────────────────────┐
│  UPF — Universal Postflight              │
│                                          │
│  1. SHA post-commit                      │
│  2. Tests impactés (grep par module)     │
│  3. Forensic delta (events post-mod)     │
│  4. Language matrix diff (si NLP touché) │
│  5. Open tasks still open ?              │
│  6. Régression baseline modules SHA      │
│  7. Rapport généré automatiquement       │
└──────────────────────────────────────────┘
        ↓
Rapport R<N+1> dans rapports/
        ↓
task_ledger mis à jour
```

### 3.2 Composants UPF — fichiers à créer

#### `scripts/artcb_r481_upf_postflight.py`

| Fonction | Entrée | Sortie | Ne pas dupliquer |
|---|---|---|---|
| `detect_modified_modules(git_diff)` | diff git | liste modules modifiés | — |
| `find_affected_tests(modules, tests_dir)` | modules | liste fichiers tests | — |
| `read_forensic_delta(ledger, sha_before, sha_after)` | JSONL, 2 SHA | events forensic post-mod | `forensic.py` existant |
| `check_language_impact(modules)` | modules modifiés | bool NLP_touched + langues affectées | `logs/R471_mapping_stats.json` |
| `check_open_tasks_still_open(ledger)` | task_ledger | tâches toujours OPEN après mod | `task_ledger.yaml` |
| `compute_module_sha_diff(baseline, current)` | 2 dicts SHA | modules dont le SHA a changé | `artcb_r394_module_fingerprints.py` |
| `generate_upf_report(results, report_dir)` | dict résultats | fichier `.md` dans `rapports/` | — |

---

## 4. Graphe d'appel récursif — la brique manquante principale

### 4.1 Problème exact

Tel que le rapport l'énonce, la vulnérabilité peut être invisible dans la fonction directement examinée :

```python
create_wallet()
    ↓ appelle
validate_user()
    ↓ appelle
check_identity()
    ↓ appelle
legacy_identity_check()   ← faille ici, 4 couches plus bas
```

Bob ne descend pas automatiquement dans cette chaîne.

### 4.2 Solution : `artcb_r481_call_graph.py`

**Algorithme (Python `ast` stdlib — zéro dépendance externe) :**

```python
# Pseudo-code — à implémenter dans R482
def build_call_graph(src_root: str) -> dict[str, set[str]]:
    """
    Parcourt tous les .py de src_root.
    Pour chaque fonction f, extrait les appels directs (ast.Call).
    Retourne {function_qname: {called_function_qnames}}.
    Détection de cycles via DFS + visited set.
    Profondeur max configurable (défaut: 10 niveaux).
    """
    ...

def find_call_chain(graph, entry: str, target: str) -> list[str] | None:
    """
    Cherche si target est atteignable depuis entry dans le graphe.
    Retourne le chemin [entry, ..., target] ou None.
    """
    ...
```

**Contrainte : ne pas utiliser `inspect` en runtime** — analyse statique `ast` uniquement, pour pouvoir tourner sans démarrer le serveur.

**Fichiers existants à ne pas recréer :**
- `scripts/artcb_r394_module_fingerprints.py` — fingerprint SHA par module (réutilisable comme baseline)
- `scripts/artcb_r375_corpus_refresh.py` — scanner AST partiel (sections à réutiliser)

### 4.3 Profondeur recommandée

| Contexte | Profondeur max | Justification |
|---|---|---|
| Audit sécurité (identity, biometric, wallet) | 15 niveaux | Risque élevé |
| Audit NLP / LexiconMapper | 8 niveaux | Chaînes moins profondes |
| Audit tokenomics / consensus | 10 niveaux | Dépendances croisées |
| Audit général | 6 niveaux | Compromis perf/couverture |

---

## 5. Corrélation quadri-axiale : Code ↔ Tests ↔ Forensic ↔ Spec

### 5.1 Matrice de concordance (à implémenter dans R482)

```
Pour chaque fonctionnalité F identifiée dans le corpus CR-* :

  SPEC(F)    = CR-* ayant domain=F et type=RULE/SPEC
  CODE(F)    = modules/fonctions ayant F dans leur nom ou docstring
  TEST(F)    = tests ayant F dans leur identifiant ou fixture
  FORENSIC(F)= events forensic ayant event_type relatif à F

  CONCORDANCE(F) :
    SPEC ∩ CODE  → couvert ?    [couverture_spec]
    CODE ∩ TEST  → testé ?      [couverture_test]
    TEST ∩ FORENSIC → prouvé ?  [couverture_runtime]
    SPEC ∩ FORENSIC → respecté ?[couverture_compliance]
```

**Format de sortie recommandé :**

```json
{
  "feature": "unique_human_identity",
  "spec_entries": ["CR-012", "CR-087"],
  "code_coverage": ["check_uniqueness", "hamming_uniqueness_check", "PaillierHammingBackend"],
  "test_coverage": ["test_p26", "test_p27", "T07_check_uniqueness"],
  "forensic_coverage": ["BIO_UNIQUENESS_OK", "BIO_UNIQUENESS_FAIL"],
  "concordance": {
    "spec_in_code": true,
    "code_in_tests": true,
    "tests_in_forensic": true,
    "spec_in_forensic": true
  },
  "anomalies": []
}
```

**Exemple de contradiction détectable automatiquement :**

```json
{
  "feature": "unique_human_identity",
  "anomalies": [{
    "type": "RUNTIME_VIOLATION",
    "spec": "HumanID must be unique",
    "unit_test": "PASS",
    "forensic_observation": "3 identical HumanIDs on 2 paths",
    "severity": "CRITICAL",
    "action_required": "find_root_cause"
  }]
}
```

---

## 6. Invariant L-100 — Couverture linguistique permanente

### 6.1 Définition

Pour toute modification touchant l'un des domaines suivants :

```
NLP | tokenizer | dictionnaire | lexique | IR | traduction |
sémantique | normalisation | résolution | POS | collision |
frontend de langue | Unicode | encodage
```

Le UPF doit automatiquement :

1. Identifier les langues potentiellement impactées (via `detect_modified_modules` + mapping module→langues)
2. Vérifier que des tests existent pour chacune de ces langues
3. Comparer les stats de résolution avant/après (baseline = `logs/R471_mapping_stats.json`)
4. Inclure dans le rapport une section `language_impact_matrix`

### 6.2 Mapping module→langues (à construire dans R482)

```python
LANGUAGE_SENSITIVE_MODULES = {
    "src/artcb/language/lexicon_mapper.py":  "all_16",
    "src/artcb/language/registry.py":         "all_16",
    "src/artcb/ir/encoder.py":                ["fr", "en"],
    "src/artcb/ir/llm_encoder.py":            ["fr", "en"],
    "src/artcb/language/concept_lexicon.py":  "all_16",
}
SUPPORTED_LANGUAGES = [
    "fr", "en", "de", "es", "it", "pt", "ru",
    "zh", "ja", "ko", "ar", "tr", "la", "nl", "pl", "sv"
]
```

---

## 7. États de tâche étendus (enrichissement task_ledger)

### 7.1 États actuels dans `task_ledger.yaml`

Vérifiés sur HEAD : `OPEN`, `IN_PROGRESS`, `DONE`, `BLOCKED`.

### 7.2 États supplémentaires recommandés

```yaml
# À ajouter dans task_ledger.yaml — sans modifier le format existant
# Nouveaux états compatibles avec le parser actuel :

OPEN           # non démarré
IN_PROGRESS    # en cours
TESTING        # code fini, tests en cours
FIXING         # test échoué, correction en cours
DONE_REPORTED  # déclaré DONE mais non vérifié sur HEAD (L-055)
DONE_VERIFIED  # vérifié sur HEAD (git show HEAD:<path> OK)
BLOCKED        # bloqué par dépendance externe
WAITING_EXTERNAL # ex: SSH N2 inaccessible, AWS CLI absent
DEFERRED       # reporté explicitement avec justification
CERTIFIED      # DONE_VERIFIED + tests PASS + forensic OK + SHA chainé
```

**Invariant :** Une nouvelle tâche ne peut pas changer le statut d'une tâche existante OPEN → DONE sans passer par TESTING + DONE_VERIFIED. Cette règle doit être vérifiable par un script `check_task_transitions.py`.

---

## 8. Priorité d'implémentation

### Phase 1 — Fix immédiat (1 ligne, R482)

```
user_prompt_submit.py ligne ~4 :
Ajouter ("STANDARD_NAMES_ARTCB", 3000, "STANDARD NAMES") dans INJECT_CONTENT_FILES
```

**Critère de DONE_VERIFIED :** L'injection est visible dans le prochain prompt (préfixe `STANDARD NAMES` dans le contexte injecté).

### Phase 2 — UAP léger (R483, ~200 lignes Python)

Fichier `scripts/artcb_r483_uap_preflight.py` :
- `get_git_sha()` + `load_task_ledger()` + `scan_open_findings()` + `build_uap_block()`
- Branché dans `user_prompt_submit.py` comme appel optionnel (fail-open si erreur)
- Tests : ≥ 15 tests unitaires

**Critère de DONE_VERIFIED :** Le bloc UAP est visible dans le contexte injecté à chaque prompt.

### Phase 3 — Graphe d'appel AST (R484, ~300 lignes Python)

Fichier `scripts/artcb_r484_call_graph.py` :
- `build_call_graph(src_root)` — analyse AST, profondeur configurable
- `find_call_chain(graph, entry, target)` — BFS/DFS avec détection cycles
- Tests : ≥ 20 tests (incluant détection cycle, profondeur max, module absent)

**Critère de DONE_VERIFIED :** `build_call_graph("src")` tourne en < 5s sur les 315 modules.

### Phase 4 — UPF + corrélation quadri-axiale (R485, ~400 lignes Python)

Fichier `scripts/artcb_r485_upf_postflight.py` :
- `detect_modified_modules()` + `find_affected_tests()` + `read_forensic_delta()`
- `check_language_impact()` + `generate_upf_report()`
- Branché dans `stop.py` comme appel post-session
- Tests : ≥ 25 tests

**Critère de DONE_VERIFIED :** Un rapport UPF est généré automatiquement dans `rapports/` après chaque session contenant une modification de code.

---

## 9. Ce que ce rapport ne fait PAS

Conformément à la demande explicite :

- ❌ Aucune modification de code dans ce rapport
- ❌ Aucune modification du hook `user_prompt_submit.py` dans ce rapport  
- ❌ Aucun nouveau fichier Python créé dans ce rapport
- ❌ Aucune affirmation de DONE sur une tâche non vérifiée

---

## 10. Résumé des fichiers existants à NE PAS dupliquer

| Fichier existant | Ce qu'il fait | Dans quelle phase UAP/UPF le réutiliser |
|---|---|---|
| `src/artcb/trace/forensic.py` | ForensicLedger JSONL | Phase 2 (scan_open_findings) + Phase 4 (forensic_delta) |
| `scripts/artcb_r394_module_fingerprints.py` | SHA modules | Phase 3 (baseline régression) |
| `scripts/artcb_r375_corpus_refresh.py` | Scanner AST partiel | Phase 3 (réutiliser le parser module) |
| `rules/task_ledger.yaml` | Tâches OPEN/IN_PROGRESS | Phase 2 (load_task_ledger) |
| `rules/rule_corpus_index.json` | 230 CR-* | Phase 4 (corrélation spec↔code) |
| `logs/R471_mapping_stats.json` | Stats 16 langues 21.5M | Phase 4 (language_baseline) |
| `data/trace/bob_turns.jsonl` | Historique turns | Phase 4 (baseline runs) |

---

## 11. `CERTIFIED_100 = false`

Ce rapport décrit une direction architecturale validée sur les preuves disponibles. Aucune des phases 2-4 n'est implémentée. Le seul fix immédiat (Phase 1 — `STANDARD_NAMES_ARTCB`) représente une modification de 1 ligne, testable en un prompt.

La certification sera possible uniquement quand :
1. Phase 1 DONE_VERIFIED ✅
2. Phase 2 DONE_VERIFIED ✅
3. Phase 3 DONE_VERIFIED ✅
4. Phase 4 DONE_VERIFIED ✅
5. Tous les tests PASS sur le SHA final
6. Forensic chain cohérent

**`CERTIFIED_100 = false`** jusqu'à ce point.
