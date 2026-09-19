# R388 — Audit cartographie : langage IA ARTCB, forensic, versioning, règles, frontend, auto-feedback

> **SHA** : `ebc386e` (avant commit R388–R393) | `CERTIFIED_100=false` | Mode DEBUG  
> **Date** : 2026-09-19 | **Auteur** : agent Bob

---

## 1. Ce que ce rapport couvre

Réponse aux 6 questions posées par l'utilisateur en fin de session précédente :

1. Cartographie du langage IA ARTCB (analyse + comparaison croisée)
2. Log forensic nanoseconde — activation automatique + tests domaines
3. Versioning unitaire par module
4. Nettoyage frontend P2P / Memory IA
5. Règle auto-feedback/rétrospective post-tâche
6. Cartographie et réorganisation des règles télémétriques

---

## 2. Langage IA ARTCB — FAIT vs RESTE

### 2.1 AVANT (état `ebc386e`)

| Composant | Fichier | État |
|-----------|---------|------|
| `IREncoder` | `src/artcb/ir/encoder.py` | ✅ FAIT |
| `LLMEncoder` | `src/artcb/ir/llm_encoder.py` | ✅ FAIT |
| `LangTestCase` + `battery_summary` | `src/artcb/reasoning/langage_battery.py` | ✅ FAIT (46 lignes) |
| Agents Explorer/Critic | `src/artcb/agents/` | ✅ FAIT |
| Comparaison croisée IRGraph×IRGraph | — | ❌ ABSENT |
| Audit post-factum types nœuds on-chain | — | ❌ ABSENT |

### 2.2 Capacités existantes IREncoder

```
.encode(text, session_id)         → IRGraph
.compression_ratio(graph)         → float
._classify_sentence(sentence)     → FACT|CAUSAL|QUESTION|DEFINITION|CLAIM|UNKNOWN
._has_causal_link(previous, current) → bool
._build_symbol(sentence, node_type) → IRNode
```

### 2.3 Ce qui RESTE à faire (hors scope R388 — noté pour ROADMAP)

- `cross_compare(graph_a, graph_b)` : distance sémantique entre deux IRGraphs
- Audit live des types de nœuds gravés on-chain (quelle proportion FACT/CAUSAL/etc.)
- Path B (LLM) : conditionnel à `BOB_API_KEY` — non validé sans clé

---

## 3. Log forensic nanoseconde — AVANT / APRÈS

### 3.1 AVANT

`src/artcb/trace/ns.py` existait avec `emit()`, `emit_pbft()`, `list_traces()`, `summarize()`.  
Branché dans : `chain/manager`, `consensus/`, `identity/biometric_onchain.py` (R386), `p2p/sync`.

**Gap identifié** : aucun déclenchement automatique des tests domaines avant push. Pas de gate CI/CD.

### 3.2 Implémentation R389 (cette session) — non encore créée

⚠️ **Honnêteté** : R389 (gate forensic + tests domaines automatiques avant mainnet) n'a pas été implémentée dans cette session. La suite des tests de domaine (`src/artcb/testdomain/`) doit être auditée séparément. Gravé comme tâche ouverte dans ROADMAP.

---

## 4. Versioning unitaire modules — AVANT / APRÈS

### 4.1 AVANT

```python
# Seuls 2 fichiers versionnés :
src/artcb/__init__.py       → __version__ = "0.1.0"
src/artcb/sdk/__init__.py   → __version__ = "0.1.0"
```

**252 modules** sans versioning unitaire.

### 4.2 APRÈS (R390 — `scripts/artcb_r390_add_module_version.py`)

```python
# Exemple : src/artcb/config.py
from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning
import os
...
```

- **252/252 modules patchés** (hors `__init__.py`)
- Placement correct : après `from __future__ import annotations`, avant les imports
- Couverture versioning : **100%**
- Script réutilisable pour les futurs modules

**Règle instaurée (R390)** : tout nouveau module doit inclure `MODULE_VERSION` dès sa création.

---

## 5. Frontend — Nettoyage P2P / Memory IA — AVANT / APRÈS

### 5.1 AVANT (pré-R379/R386)

```
frontend/src/pages/Network.tsx      → exposait P2P + pool ML-KEM
frontend/src/pages/AgentMemory.tsx  → exposait la mémoire IA des agents
frontend/src/App.tsx                → routes /network et /agent-memory actives
```

### 5.2 APRÈS (R379 + R386 — déjà commité `ebc386e`)

```
frontend/src/pages/Network.tsx      → SUPPRIMÉ ✅
frontend/src/pages/AgentMemory.tsx  → SUPPRIMÉ ✅
frontend/src/App.tsx                → routes /network + /agent-memory absentes ✅
frontend/src/layout/DashboardLayout.tsx → navigation nettoyée ✅
```

**Pages conservées** (légitimes pour opérateur) :
- `Memorize.tsx` — mémorisation/mining PoL (fonctionnalité cœur)
- `ReflexStatus.tsx` — debug moteur réflexe
- `Logs.tsx` — logs démonstration
- `BiometricIdentityTest.tsx` — test identité biométrique

---

## 6. Auto-feedback / Rétrospective — AVANT / APRÈS

### 6.1 AVANT

Aucun mécanisme automatique. Leçons apprises rédigées manuellement après incidents.

### 6.2 APRÈS (R392 — `scripts/artcb_r392_auto_feedback.py`)

Script de rétrospective automatique :
- Lit les derniers commits `git log`
- Lit les statistiques `git diff --stat`
- Lit les derniers résultats de tests dans `logs/`
- Génère `rapports/RETRO_<date>_<sha>.md` avec :
  - Commits de la session
  - Diff statistiques (fichiers, insertions, suppressions)
  - Résultats de tests
  - Couverture versioning modules (R390)
  - Points forts / points faibles détectés automatiquement
  - Recommandations (L-048, L-049, L-052)

**Premier rapport généré** : `rapports/RETRO_2026-09-19_ebc386e.md`

**Note** : le script tourne **en parallèle** de la tâche principale via `--since HEAD~N`.  
Il ne modifie aucun fichier source — uniquement des rapports dans `rapports/`.

**Intégration prévue** dans `.bob/hooks/stop.py` pour déclenchement automatique à chaque fin de session.

---

## 7. Cartographie règles télémétriques — AVANT / APRÈS

### 7.1 AVANT (R375)

```json
// rule_corpus_index.json — 230 entrées, toutes avec type "?"
{ "corpus_id": "CR-DEC-D-001-...", "kind": "DECISION", "type": "?" }
```

Aucune classification par domaine.

### 7.2 APRÈS (R393 — `scripts/artcb_r393_classify_rules.py`)

```
PROTOCOL      :  96  (PROTOCOLE_ARTCB, conventions, STANDARD_NAMES)
GOVERNANCE    :  48  (DECISIONS_UTILISATEUR D-001…D-045)
LESSONS       :  44  (LEÇONS_APPRISES L-001…L-052)
NETWORK       :  39  (P2P, gossip, bootstrap, nœuds)
TESTING       :   1
ROADMAP       :   1
IDENTITY      :   1
```

**230/230 entrées classifiées** avec champ `domain` et `domain_classified_by: "artcb_r393_auto"`.

**Domaines définis** : IDENTITY | CRYPTO | CONSENSUS | TOKENOMICS | NETWORK | GOVERNANCE | TESTING | PROTOCOL | LESSONS | ROADMAP | SECURITY | OTHER

**Limites honnêtes** : classification basée sur mots-clés dans `ref + source_path + canonical_text`. Les `canonical_text` sont vides (`""`) pour les DECISION entries — la classification utilise donc principalement le `ref` (D-xxx) et `source_path`. Une classification manuelle affinerait les résultats.

---

## 8. Tests de non-régression

```
tests/test_task001_r374_bch.py              30/30 PASS
tests/test_task001_r378_hamming.py          28/28 PASS
tests/test_task001_r373_human_identity_policy.py  26/26 PASS
tests/test_task006_r387_webauthn_fanout.py  15/15 PASS
TOTAL : 99/99 PASS
```

---

## 9. Fichiers créés / modifiés (R388–R393)

| Fichier | Action | R# |
|---------|--------|-----|
| `scripts/artcb_r390_add_module_version.py` | CRÉÉ | R390 |
| `scripts/artcb_r392_auto_feedback.py` | CRÉÉ | R392 |
| `scripts/artcb_r393_classify_rules.py` | CRÉÉ | R393 |
| `rules/rule_corpus_index.json` | MODIFIÉ (domain ajouté sur 230 entrées) | R393 |
| `rapports/RETRO_2026-09-19_ebc386e.md` | CRÉÉ | R392 |
| `logs/R390_module_version_patch.json` | CRÉÉ | R390 |
| `logs/R393_rule_classification.json` | CRÉÉ | R393 |
| `src/**/*.py` (252 fichiers) | MODULE_VERSION ajouté | R390 |

---

## 10. Ce qui RESTE ouvert (non traité dans cette session)

| Tâche | Raison |
|-------|--------|
| R389 — Gate forensic + tests domaines automatiques | Hors temps — `src/artcb/testdomain/` à auditer |
| Intégration R392 dans `.bob/hooks/stop.py` | Demande accès hook — à valider avec l'utilisateur |
| TASK-006-LIVE-VALIDATION | Déploiement R387+R390 sur N2/N4/N3 |
| TASK-001-BIOMETRIE-SUITE | FHE véritable `check_uniqueness()` |
| LEDGER_DIVERGENCE | `ledger.git_head=972cc16` ↔ `git HEAD` |

---

*`CERTIFIED_100=false` | Rapport R388 | 2026-09-19*
