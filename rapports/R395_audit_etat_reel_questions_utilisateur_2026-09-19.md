# R395 — Audit état réel : réponses aux questions utilisateur

**Date :** 2026-09-19  
**SHA git HEAD :** 60be7a5  
**Référence :** Questions utilisateur session 2026-09-19-II  
**CERTIFIED_100 :** false  
**Mode :** DEBUG actif  

---

## Contexte

L'utilisateur observe le message `{"code":"device_wallet_limit","message":"Un wallet 'w-55fe5464a470b6ed' a déjà été créé sur cet appareil..."}` et pose 7 questions distinctes sur l'état du projet.

Ce rapport audite chaque question avec le code source réel et les logs disponibles.

---

## 1. `device_wallet_limit` — Fonctionnement confirmé ✅

### Avant (R345, R358)
```
Aucun mécanisme d'admin reset.
L'utilisateur ne pouvait pas se débloquer sans modifier manuellement
data/wallet_device_bindings.json sur le serveur.
```

### Après (R379 — actuel sur 60be7a5)

Le message observé est le **comportement attendu et correct** :

```json
{
  "code": "device_wallet_limit",
  "message": "Un wallet 'w-55fe5464a470b6ed' a déjà été créé sur cet appareil (fingerprint: 97a0b6403ecb4932…).",
  "hint": "Un seul wallet par appareil navigateur. WebAuthn ≠ HumanIdentity unique mondiale.",
  "unique_human_proven": false
}
```

Implémentation : `src/artcb/security/wallet_device_binding.py` L.175–180.

**Admin reset opérationnel depuis R379 :**
- Fichier : `src/api/admin_device_binding_routes.py`
- Enregistré : `src/api/main.py` L.453
- Endpoints disponibles :
  - `GET    /api/v1/admin/device-binding/list`
  - `DELETE /api/v1/admin/device-binding/fingerprint/{fingerprint}`
  - `DELETE /api/v1/admin/device-binding/wallet/{wallet_name}`
  - `DELETE /api/v1/admin/device-binding/test/wallet/{wallet_name}`

**Pour débloquer le fingerprint `97a0b6403ecb4932` :**
```bash
curl -X DELETE "https://artcb.me/api/v1/admin/device-binding/fingerprint/97a0b6403ecb4932" \
  -H "Authorization: Bearer <api_key_operateur>"
```
L'appareil pourra alors recréer un wallet proprement.

---

## 2. Audit du langage IA ARTCB — Ce qui est déjà fait ✅

### Capacités existantes confirmées dans le code

| Capacité | Fichier source | Statut |
|----------|---------------|--------|
| Classification phrases → FACT/REASON/GOAL/PROOF/EVENT/DECISION/HYPOTHESIS/CONTEXT | `src/artcb/ir/encoder.py:271` | ✅ ACTIF |
| Encodage dual-path rule-based (A) + LLM Bob (B) | `src/artcb/ir/llm_encoder.py` | ✅ ACTIF |
| ConceptID cross-langue (FR/EN/ES/ZH/RU → même ID) | `src/artcb/ir/concept.py` | ✅ VALIDÉ |
| Analyse sémantique : action_code, object_codes, modifier_codes | `src/artcb/ir/concept_lexicon.py` | ✅ ACTIF |
| Comparaison croisée nœuds multi-hôtes (C2D) | `logs/316_langage_ia_matrix_latest.json` | ✅ PASS |
| Smart contracts déclaratifs IR v0.2 | `src/artcb/ir/rules.py` | ✅ ACTIF |
| IR binaire natif + zstd | `src/artcb/ir/binary.py` | ✅ ACTIF |
| Classification 230 règles par domaine | `rules/rule_corpus_index.json` | ✅ ACTIF (R393) |
| Mémoire cross-session (ConceptStore) | `src/artcb/memory/concept_store.py` | ✅ backend uniquement |

### Log de validation croisée existant

`logs/316_langage_ia_matrix_latest.json` confirme :
```json
{
  "verdict": {
    "live_probe_fr_en_es_overlap": "PASS",
    "live_universal_voiture_car_coche": "PASS",
    "c2d_multihote_pass": true,
    "c2d_five_store_fanout_pass": true
  },
  "agent_ab": {
    "phrase_shared": true,
    "lemma_shared": true,
    "note": "FR/ZH/RU same ConceptIDs without shared UTF-8 surface forms"
  }
}
```

### Ce qui reste à faire (TASK-001)
- Comparaison biométrique FAR/FRR sur vraies empreintes (seuil Hamming non calibré sur données réelles)
- Matching FHE chiffré pour `check_uniqueness()` — actuellement Hamming direct (R378)

---

## 3. Système de log forensic nanoseconde — État réel ✅ / ⚠️

### Avant (pré-R386)
```
Logs uniquement au niveau INFO/DEBUG Python standard.
Pas de granularité nanoseconde sur les opérations non-HTTP.
```

### Après (R386 — actuel sur 60be7a5)

**Actif automatiquement pour :**

| Domaine | Déclencheur | Fichier trace |
|---------|-------------|---------------|
| Toutes requêtes HTTP | Middleware FastAPI | `trace/ns.jsonl` |
| Consensus PBFT | `emit_pbft()` dans `consensus/pbft_*.py` | `trace/ns.jsonl` |
| Opérations biométriques | `biometric_onchain.py:578` et `717` | `trace/ns.jsonl` |
| Admin device binding | `admin_device_binding_routes.py:62` | `trace/ns.jsonl` |
| Écriture de blocs blockchain | `chain/manager.py` | `trace/ns.jsonl` |

**Format de chaque ligne :**
```json
{"ts_ns": 1789..., "mono_ns": 1234..., "pid": 1234, "kind": "...", "dur_ns": ...}
```

**⚠️ Point manquant — règle NON activée sur les tests pytest :**

Les runs pytest locaux ne poussent pas d'événements dans `trace/ns.jsonl`. 
Le log forensic est un log d'exécution runtime (serveur live), pas un log de CI.
Pour qu'il soit complet sur chaque modification de code, il faudrait :
- Un hook pytest `conftest.py` qui émette un événement `trace/ns.jsonl` à chaque test PASS/FAIL
- Ce n'est pas encore implémenté → **TÂCHE FUTURE identifiée**

---

## 4. Versioning unitaire de chaque fichier/module — État réel ✅

### Avant (pré-R390)
```
Aucun numéro de version dans les modules Python.
Impossible de tracer quelle version d'un module était active sur un nœud.
```

### Après (R390 — actuel sur 60be7a5)

**253 fichiers Python** portent la ligne :
```python
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning
```

Script de maintenance : `scripts/artcb_r390_add_module_version.py`

**Fingerprint SHA-256 des modules :** `logs/R394_module_fingerprints.json`

**⚠️ Règle L-053 à respecter :**
L'ordre correct après chaque session de dev :
```
développement → tests PASS → git commit → fingerprint-only → git add artefact → commit (ou amend) → push
```
Jamais générer le fingerprint avant le commit final.

---

## 5. Suppression P2P/Memory IA du frontend — DÉJÀ FAIT ✅

### Avant (pré-R379)
```
/network et /agent-memory présents dans le menu de navigation frontend.
Les utilisateurs avaient accès direct aux outils P2P et mémoire IA.
```

### Après (R379 — actuel sur 60be7a5)

Fichier : `frontend/src/App.tsx` L.1–4 :
```typescript
// R379 — Supprimé du frontend : /agent-memory (P2P IA), /network (P2P pairs + pool ML-KEM)
// Backend AgentMemory, P2P, Network : conservés — agents/API uniquement
```

Fichier : `frontend/src/layout/DashboardLayout.tsx` L.19 :
```typescript
// R379 — nav publique : /network (P2P/pool) et /agent-memory (mémoire IA) supprimés
```

**Navigation actuelle (publique) :**
- CORE : Dashboard, Register, Add Device, Graph
- CHAIN : Chain, Wallets, Mining
- SYSTEM : System, Console, Integrations, Governance, Groups, API Keys

**Backends conservés (API/agents uniquement) :**
- P2P : `src/artcb/p2p/`, routes `src/api/p2p_routes.py`, `src/api/libp2p_routes.py`
- Memory IA : `src/artcb/memory/`, routes `src/api/concept_routes.py`

**Aucune action requise sur ce point.**

---

## 6. Règle d'auto-feedback/rétrospective — État réel ✅

### Avant (pré-R392)
```
Aucun mécanisme automatique de rétrospective.
L'agent devait être explicitement sollicité pour évaluer ses performances.
```

### Après (R392 + R394-C — actuel sur 60be7a5)

**Mécanisme actif :**

1. **Script R392** : `scripts/artcb_r392_auto_feedback.py`
   - Analyse : faits git (commits, fichiers modifiés), tests PASS/FAIL/régression, couverture MODULE_VERSION, CERTIFIED_100
   - Produit : `rapports/RETRO_<date>_<sha>.md` avec FAITS / OBSERVATIONS / RISQUES / LEÇONS / ACTIONS

2. **Déclenchement automatique** : `.bob/hooks/stop.py` L.119–127
   ```python
   # --- R394-C : Auto-feedback post-session (fail-open) ---
   subprocess.run(["python3", "scripts/artcb_r392_auto_feedback.py", "--since", "HEAD~1"], ...)
   ```

3. **Séparation dev/user** : `capture_output=True` → le feedback tourne en parallèle sans polluer le contexte de développement

**⚠️ Point faible connu :** Si le subprocess échoue silencieusement, aucune trace d'échec n'est créée dans `bob_turns.jsonl`. Ce serait l'objet d'une future amélioration (compteur succès/échec hook).

---

## 7. Cartographie des règles télémétriques — État réel ✅ / ⚠️

### Architecture actuelle (R375 — actuel sur 60be7a5)

**Deux niveaux :**

| Niveau | Fichier | Taille | Description |
|--------|---------|--------|-------------|
| CORPUS | `rules/rule_corpus_index.json` | 230 CR-* | RULE/DECISION/SPEC/LESSON/CHECK/CONVENTION/QUESTION/EVIDENCE |
| REGISTRY | `rules/rule_registry.json` | 20 RT-* | Règles opérationnelles actives |
| SOURCES | `rules/rule_sources.json` | 18 sources | SHA256, autorité, détections par source |
| COVERAGE | `rules/rule_coverage.json` | 148 marqueurs | Couverture honnête |

**Classification par domaine existante (R393) :**
Les 230 CR-* sont classifiés avec `confidence` et `domain`. Exemple de domaines détectés :
- CONSENSUS / NETWORK / SECURITY / IDENTITY / BIOMETRICS / TOKENOMICS / GOVERNANCE
- DEBUGGING / LOGGING / VERSIONING / TESTING / DEPLOYMENT

**⚠️ Limites documentées (R375) :**

| Limite | Statut |
|--------|--------|
| Classification CR-* manuelle → automatique | ❌ non fait |
| `GOUVERNANCE_ARTCB.md` absent des sources | ❌ manquant |
| agent_id Bob/Cursor absent des compteurs | ❌ manquant |
| Réorganisation automatique au bon domaine selon usage | ❌ non fait |
| Règles télémétriques déclenchées sur CHAQUE nouvelle fonctionnalité | ⚠️ partiellement — RT-TELEMETRY actif mais pas hook CI |

---

## Résumé : déjà fait vs reste à faire

| Question | Déjà fait | Reste à faire |
|----------|-----------|---------------|
| Admin reset device | ✅ R379 complet | — |
| Langage IA cartographie | ✅ R375+R393 | FAR/FRR réels TASK-001 |
| Log forensic nanoseconde | ✅ R386 (runtime) | Hook pytest pour CI |
| Versioning unitaire | ✅ R390 (253 modules) | Maintien L-053 |
| Frontend P2P/Memory supprimé | ✅ R379 | — |
| Auto-feedback rétrospective | ✅ R392+R394-C | Compteur succès/échec hook |
| Règles télémétriques catégorisées | ✅ R375+R393 (partial) | Classification auto + GOUVERNANCE |

**Avancement global ARTCB : 76%** (inchangé — ce rapport ne modifie pas de code)

---

## Actions identifiées pour les prochaines sessions

1. **TASK-001 suite** : calibrage seuil Hamming sur vraies empreintes biométriques (FAR/FRR réels)
2. **Hook pytest CI** : ajouter `conftest.py` émettant dans `trace/ns.jsonl` à chaque test PASS/FAIL
3. **Règles auto-catégorisation** : script qui range les nouvelles CR-* dans le bon domaine automatiquement
4. **GOUVERNANCE_ARTCB** : ajouter dans `rule_sources.json` comme source manquante

---

*Rapport généré par l'agent Bob IDE — CERTIFIED_100=false | git HEAD 60be7a5*  
*Format PROTOCOLE_ARTCB : avant/après, lignes exactes, fichier source.*
