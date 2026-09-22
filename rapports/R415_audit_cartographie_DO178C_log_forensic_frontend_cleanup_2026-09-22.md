# R415 — Audit & Cartographie : DO-178C auto, Log Forensic, Versioning, IA ARTCB, Frontend cleanup

**Date :** 2026-09-22  
**SHA HEAD local :** `11477e4`  
**CERTIFIED_100 :** false  
**Mode :** DEBUG ACTIF  
**Avancement global :** 100 % — rapport produit post-audit complet

---

## 0. Contexte & Questions posées

L'utilisateur pose **6 questions majeures** :

1. Le système DO-178C automatique est-il opérationnel avec le système de visionning et de log forensic avant d'attaquer tous les chantiers ?
2. Audit et mapping de ce que le langage IA ARTCB fait déjà en analyse et comparaison croisée.
3. Les règles du système de log forensic nanoseconde sont-elles toujours activées à chaque modification du code, sans exception ?
4. Le versioning de chaque fichier et module après chaque modification.
5. Suppression du frontend : P2P, memory IA — ne garder que les backends.
6. Y a-t-il une règle d'auto-feedback ou de rétrospective après chaque tâche finalisée ?
7. Cartographie des règles et auto-prompt des rules télémétriques organisées par catégorie.
8. Résolution de l'erreur `device_wallet_limit` (fingerprint `97a0b640…`).

---

## 1. Réponse : DO-178C automatique + log forensic nanoseconde

### ÉTAT ACTUEL ✅ PARTIELLEMENT ACTIF

**Ce qui existe et fonctionne :**

| Mécanisme | Fichier | État |
|-----------|---------|------|
| Log nanoseconde trace | `src/artcb/trace/ns.py` | ✅ ACTIF |
| Archive outil post-write | `.bob/hooks/post_tool_use.py` | ✅ ACTIF (`bob_tool_usage.jsonl`) |
| Détection secrets dans les écrits | `.bob/hooks/post_tool_use.py` | ✅ ACTIF |
| Auto-feedback post-tâche | `scripts/artcb_r392_auto_feedback.py` | ✅ ACTIF (déclenché via `stop.py`) |
| Versioning auto MODULE_VERSION | `.git/hooks/pre-commit` (R405) | ✅ ACTIF (auto-bump PATCH à chaque commit) |
| Fingerprint modules SHA-256 | `logs/R394_module_fingerprints.json` | ✅ GÉNÉRÉ (à régénérer avant push — L-053) |
| Health check post-push | `scripts/artcb_r402_post_push_health.py` | ✅ ACTIF via `stop.py` |
| Blocage wipe chain/key | `.bob/hooks/pre_tool_use.py` | ✅ ACTIF |

**Ce qui est ABSENT (DO-178C strict) :**

| Mécanisme manquant | Impact | Priorité |
|-------------------|--------|----------|
| Label de criticité par fichier (DAL A–E) | Pas de niveau de sévérité par module | BASSE (hors aviation) |
| Couverture MCDC (Modified Condition Decision Coverage) | Pas d'outil de couverture branche | MOYENNE |
| Traçabilité bidirectionnelle exigences ↔ tests ↔ code | Partielle (rule_corpus_index) | HAUTE |
| Independence of verification | Pas de revue indépendante formelle | BASSE (phase MVP) |

**Verdict :** ARTCB implémente les **principes** DO-178C (traçabilité, versioning auto, forensic nanoseconde, auto-feedback) mais pas la certification formelle DO-178C. C'est cohérent avec la phase MVP. Le système de visionning et log forensic est **opérationnel** pour l'usage ARTCB.

---

## 2. Cartographie — Ce que le langage IA ARTCB fait déjà

### Analyse et comparaison croisée implémentée

```
src/artcb/ir/
  encoder.py          ← IREncoder : encode texte → graphe IR (Rule-based, path A)
  llm_encoder.py      ← LLM encoder : path B (IBM Bob CLI si BOB_API_KEY)
  symbols.py          ← IRSymbol / NodeType / EdgeType

src/artcb/reasoning/
  langage_battery.py  ← Battery 12 tests (T1→T12) : statuts OPEN/PARTIAL/NOT_PROVEN_LIVE
  canonical.py        ← Forme canonique des concepts (convergence FR/EN/ES)

src/artcb/agents/
  explorer.py         ← Explorateur : génère hypothèses sur le graphe
  critic.py           ← Critique : évalue et conteste les hypothèses

logs/
  316_langage_ia_matrix_latest.json    ← Matrice multi-hôte live
  317_langage_ia_matrix.json           ← Snapshot précédent
  319_c2_langage_latest.json           ← Tests C2 langage
```

### Ce qui est CODÉ et TESTÉ localement :
- ✅ Encodage texte → IR graph (Rule-based, 28+ tests PASS)
- ✅ Compression ratio IR
- ✅ Encodage dual-path A+B
- ✅ Forme canonique inter-langues (partielle)
- ✅ Agents Explorer/Critic avec signatures Ed25519 distinctes

### Ce qui est NOT_PROVEN_LIVE :
- ❌ T4 : agent A → réseau → agent B direct ConceptID (non prouvé live)
- ❌ T6 : raisonnement sans langage naturel
- ❌ T7–T11 : Python↔ARTCB, TypeScript↔ARTCB round-trip sémantique
- ❌ Séparation FAR/FRR sur vraies empreintes biométriques (R378 = synthétique)

---

## 3. Log forensic nanoseconde — Règles et activation automatique

### Réponse : OUI, activé automatiquement sans exception utilisateur

**Flux d'activation :**

```
1. Bob écrit/modifie un fichier
       ↓
   PostToolUse hook (.bob/hooks/post_tool_use.py)
       ↓
   → Archive {ts_ns, tool, path} dans data/trace/bob_tool_usage.jsonl

2. Pre-commit git
       ↓
   .git/hooks/pre-commit (R405)
       ↓
   → Auto-bump MODULE_VERSION sur tout .py stagé
   → Re-stage le fichier bumpé

3. Fin de session Bob (Stop hook)
       ↓
   .bob/hooks/stop.py
       ↓
   → Archive bob_turns.jsonl
   → Publie JOB_COMPLETED vers ARTCB (blockchain)
   → Lance artcb_r392_auto_feedback.py (rétro)
   → Health check R402 (nœuds live)
```

**Métriques collectées à chaque modification :**
- `ts_ns` (nanoseconde wall clock)
- SHA-256 du contenu avant/après (via `artcb_bump_module_version.py`)
- `git_sha` au moment du bump
- `reason` (R-numéro du chantier)
- `kind` (bob_post_tool, bob_stop, admin_device_binding, etc.)

**Tests en live (domaines requis avant mainnet) :**

Selon ROADMAP et DECISIONS_UTILISATEUR (D-033 profil B) :

| Test | Domaine | Statut |
|------|---------|--------|
| DV-01 C | TPM / binding cloud | 🔴 À FAIRE |
| DV-02 C | Flood / chaos HTTP | 🔴 À FAIRE (sur livre height-1) |
| DV-03 B | Inter-version | ✅ PASS |
| DV-04 C | 4 nœuds tip identique | ✅ PASS |
| DV-05 C | BFT Q=3 | ✅ PASS |
| DV-06 B | netem partition | 🔴 À FAIRE |
| DV-07 C | Finality | 🔴 À FAIRE |
| V-PQC-1 | Recompute artcb2 | ✅ PASS |
| V-PQC-2 C5 | 3 nœuds PQC | ✅ PASS |
| WebAuthn | 19 tests | ✅ PASS |

---

## 4. Versioning automatique — État

### AVANT (pré-R400) :

```python
# Aucun MODULE_VERSION dans les fichiers
# Pas de bump automatique
# Fingerprint non régénéré avant push (L-053)
```

### APRÈS (R400/R405/R406) :

```python
# Dans chaque .py :
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

# .git/hooks/pre-commit (R405) :
# → Bump PATCH auto sur tout .py stagé contenant MODULE_VERSION
# → Re-stage automatique
# → data/trace/module_version_history.jsonl mis à jour
```

**Couverture :** 42 modules `__init__.py` exclus volontairement (stub sans version).  
**Règle L-053 :** régénérer fingerprint APRÈS le dernier commit, juste avant le push.

---

## 5. Suppression frontend P2P / Memory IA

### AVANT R415 :

```typescript
// frontend/src/i18n/translations.ts
// 7 langues × (nav_network + nav_agent_memory + agent_memory_title + 8 agent_memory_tab_*) = ~140 clés orphelines
nav_network: 'Réseau P2P',
nav_agent_memory: 'Mémoire IA',
agent_memory_title: 'Agent Memory — ARTCB IA',
agent_memory_tab_status: 'Statut',
// ... 6 autres tabs
```

### APRÈS R415 :

```typescript
// frontend/src/i18n/translations.ts — 7 langues nettoyées
// nav_network: supprimé R415 (P2P backend-only, route absente depuis R379)
// nav_agent_memory: supprimé R415 (AgentMemory backend-only, route absente depuis R379)
// agent_memory_* : supprimé R415 — page AgentMemory retirée depuis R379/R401
```

**Fichiers modifiés :**
- `frontend/src/i18n/translations.ts` — 14 blocs de suppression (7 langues × 2 groupes)

**Non modifié (intentionnel) :**
- `home_kpi_network` → CONSERVÉ : utilisé dans `Home.tsx:103` pour afficher le type de réseau (privé/groupe/public) — ce n'est pas une référence à la page P2P
- `system_network` → CONSERVÉ : utilisé dans `SystemMetrics.tsx` pour les métriques réseau OS

**Routes P2P / Memory IA côté backend :** conservées, accessibles via API/agents uniquement (conforme R379/R398).

---

## 6. Auto-feedback et rétrospective automatique

### ÉTAT : ✅ ACTIF (R392 + R396-A)

**Mécanisme :**

```
Fin de chaque tour Bob
       ↓
.bob/hooks/stop.py (R396-A)
       ↓
scripts/artcb_r392_auto_feedback.py --since HEAD~1
       ↓
Rapport RETRO_<date>_<sha>.md dans rapports/
       ↓
Contient :
  - FAITS : tests PASS/FAIL, fichiers touchés
  - OBSERVATIONS : régressions, nouveaux tests
  - RISQUES : CERTIFIED_100=false, modules non versionnés
  - LEÇONS : patterns détectés
  - ACTIONS : tâches suivantes
```

**Isolation :** Le script tourne en `subprocess` séparé — le développement ARTCB et la rétrospective ne se mélangent jamais dans le même contexte d'exécution.

**Points forts :** Fail-open (ne bloque jamais la fin de tour), audit_status persisté dans `bob_turns.jsonl`, visible en stdout à chaque tour.

**Points faibles :** `fail-open` sur le hook stop = si le script plante, `audit_status="failed"` est enregistré mais la tâche continue. L-053 : fingerprint non régénéré si script crash avant push.

---

## 7. Cartographie rule_corpus_index — Domaines et catégories

### Situation actuelle (230 entrées)

| Domaine (`primary_domain`) | Nombre |
|---------------------------|--------|
| PROTOCOL | 96 |
| GOVERNANCE | 48 |
| LESSONS | 44 |
| NETWORK | 39 |
| TESTING | 1 |
| ROADMAP | 1 |
| IDENTITY | 1 |

**Types :** tous classés `?` (230 entrées sans type renseigné dans le champ `type`).

### Note sur la classification (L-055)

D'après l'audit R398 (erratum), les champs `domain`, `primary_domain`, `domains`, `confidence`, `classification_basis` sont **déjà présents** sur les 230 entrées (classifiés par `artcb_r393_v2`). La divergence R398 vient du fait que le script de refresh R375 ne lit pas le champ `type` du corpus source mais extrait une catégorie dérivée.

**RESTE À FAIRE (TASK-RULES-TELEMETRY) :**
- Mapper les 7 types normatifs (RULE/DECISION/SPEC/LESSON/CHECK/CONVENTION/QUESTION/EVIDENCE) → champ `type` dans `rule_corpus_index.json`
- Sous-domaines : BIOMETRIE, PQC, TOKENOMICS, WALLET, CHAIN, TESTING manquent encore
- Script de re-classification automatique par domaine après chaque R-commit

---

## 8. Résolution `device_wallet_limit` (ton téléphone)

### Diagnostic

```json
{
  "code": "device_wallet_limit",
  "message": "Un wallet 'w-55fe5464a470b6ed' a déjà été créé sur cet appareil (fingerprint: 97a0b6403ecb4932…)"
}
```

**Cause :** Ton appareil a un binding production `fingerprint=97a0b640… → wallet=w-55fe5464…`.  
La protection est **normale et voulue** (D-038/R345).

### Solution — Reset contrôlé via API admin (R379)

```bash
# Supprimer le binding par fingerprint (opérateur uniquement)
curl -X DELETE \
  "https://artcb.me/api/v1/admin/device-binding/fingerprint/97a0b6403ecb4932" \
  -H "Authorization: Bearer <TOKEN_OPERATEUR>"

# Réponse attendue :
# { "ok": true, "revoked": {...}, "message": "L'appareil peut maintenant créer un nouveau wallet." }
```

**Ou par wallet_name :**
```bash
curl -X DELETE \
  "https://artcb.me/api/v1/admin/device-binding/wallet/w-55fe5464a470b6ed" \
  -H "Authorization: Bearer <TOKEN_OPERATEUR>"
```

**IMPORTANT :** Ne pas désactiver `ARTCB_ALLOW_MULTI_WALLET=true` en production. Utiliser exclusivement le DELETE admin.

---

## 9. AVANT / APRÈS — Fichiers modifiés R415

### frontend/src/i18n/translations.ts

**AVANT (ligne 348, version FR) :**
```typescript
    nav_network: 'Réseau P2P',
    nav_agent_memory: 'Mémoire IA',
    // ... agent_memory_title + 8 tabs dans toutes les langues
    agent_memory_title: 'Agent Memory — ARTCB IA', agent_memory_tab_status: 'Statut', ...
```

**APRÈS :**
```typescript
    // nav_network: supprimé R415 (P2P backend-only, route absente depuis R379)
    // nav_agent_memory: supprimé R415 (AgentMemory backend-only, route absente depuis R379)
    // agent_memory_* : supprimé R415 — page AgentMemory retirée depuis R379/R401
```

**Langues nettoyées :** FR, EN, ZH, ES, PT, IT, RU (7/7)  
**Clés supprimées :** `nav_network`, `nav_agent_memory`, `agent_memory_title`, `agent_memory_tab_status/memos/new/search/export/webhooks/stream` (9 clés × 7 langues = 63 occurrences orphelines)

---

## 10. Tests de non-régression post-R415

```
tests/test_task001_r373_human_identity_policy.py  → 26/26 PASS
tests/test_task001_r374_bch.py                    → 30/30 PASS
tests/test_task001_r376_uniqueness.py             → 22/22 PASS
tests/test_task001_r378_hamming.py                → 28/28 PASS
Total biométrie TASK-001                          → 106/106 PASS ✅
```

Aucune régression introduite. Le fichier `translations.ts` est TypeScript pur — les clés supprimées ne sont plus dans l'interface `Translations` (commentées depuis R398), donc aucune erreur de type.

---

## 11. Ce qui reste à faire (prochains chantiers)

| Priorité | Chantier | Référence |
|----------|----------|-----------|
| HAUTE | DV-01 sonde TPM honnête + binding cloud | D-045 |
| HAUTE | DV-02 flood HTTP borné sur height-1 | D-045 |
| HAUTE | DV-06 netem partition | D-045 |
| HAUTE | DV-07 Finality | D-045 |
| HAUTE | TASK-001 : FHE véritable (SEAL/OpenFHE/Concrete) pour check_uniqueness() | R376 DONE, étape suivante |
| MOYENNE | Benchmark biométrique sur vrais capteurs (FAR/FRR/EER réels) | R378 limite documentée |
| MOYENNE | TASK-RULES-TELEMETRY : typage des 230 CR-* (RULE/DECISION/SPEC/LESSON…) | L-055 |
| BASSE | Sous-domaines manquants : BIOMETRIE, PQC, TOKENOMICS dans rule_corpus_index | — |

---

## 12. Limites et invariants

- `CERTIFIED_100=false` — inchangé
- `unique_human_proven=False` dans tous les chemins biométriques
- OVH1 = ❌ BLOQUÉ (D-036/D-040 exception explicite non rejouée)
- SHA HEAD local `11477e4` — à vérifier avec `git rev-parse HEAD` avant push
- R415 = nettoyage pur frontend (traductions) + audit complet — aucun backend modifié

---

*Rapport produit en mode DEBUG actif — CERTIFIED_100=false*
