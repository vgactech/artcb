# R401 — Audit cartographie DONE/RESTE + Frontend cleanup + Auto-feedback enrichi

**Date** : 2026-09-21  
**SHA HEAD** : `18aaa8f` (avant commit R401)  
**CERTIFIED_100=false** | Mode DEBUG actif

---

## 1. Réponse à la question : Qu'est-ce qui existe déjà / reste à faire ?

### 1.1 Cartographie : Langage IA ARTCB — analyse et comparaison croisée

| Capacité | État | Module(s) concerné(s) |
|----------|------|-----------------------|
| Encodage rule-based (IREncoder) | ✅ DONE | `src/artcb/reasoning/ir_encoder.py` |
| Encodage LLM Bob (path B) | ✅ DONE | `src/artcb/reasoning/llm_encoder.py` |
| Comparaison croisée XOR (SHA-256) | ✅ DONE — R376 | `biometric_onchain.py` |
| Comparaison Hamming directe | ✅ DONE — R378 | `biometric_onchain.py` |
| BCH FuzzyExtractor tolérant bruit | ✅ DONE — R374 | `biometric_onchain.py` |
| Politique identité humaine 5 cas | ✅ DONE — R373 | `human_identity_policy.py` |
| check_uniqueness() branché matching | ✅ DONE — R376 | `biometric_onchain.py` |
| FAR/FRR sur capteurs réels | ❌ RESTE | TASK-001 — capteurs requis |
| Calibrage seuil Hamming (vrais doigts) | ❌ RESTE | TASK-001 — données expérimentales |
| FHE véritable (SEAL/OpenFHE/Concrete) | ❌ RESTE | TASK-001 — décision après FAR/FRR |

### 1.2 Log forensic nanoseconde

| Règle | État | Preuve |
|-------|------|--------|
| Trace nanoseconde HTTP (middleware) | ✅ ACTIF | `src/api/main.py:162` `nanosecond_http_trace` |
| Trace ns opérations biométriques | ✅ ACTIF — R386 | `biometric_onchain.py:578` + `:717` |
| Trace ns PBFT | ✅ ACTIF | `src/artcb/trace/ns.py` |
| Trace ns opérations admin binding | ✅ ACTIF — R379 | `admin_device_binding_routes.py:63` |
| Trace ns concept routes | ✅ ACTIF | `src/api/concept_routes.py:83` |
| Auto-déclenchement à chaque modif | ⚠️ PARTIEL | Middleware HTTP couvre les routes ; les fonctions non-HTTP (biometric) ont leur propre trace — **pas de déclenchement automatique sur modification de code** |
| Log forensic avant chaque test domaine | ❌ RESTE | À formaliser dans les suites pytest |

> **Note** : Le log forensic est activé **en production** (runtime). Il n'est pas activé automatiquement à chaque modification de code source. C'est une distinction importante : modifier `biometric_onchain.py` ne produit pas de log — exécuter `enroll_biometric()` sur une instance live oui.

### 1.3 Versioning fichier/module après modification

| Mécanisme | État | Script |
|-----------|------|--------|
| Ajout initial MODULE_VERSION à tous les modules | ✅ DONE — R390 | `scripts/artcb_r390_add_module_version.py` |
| 175 modules versionnés (1.0.0) | ✅ DONE | scan `grep MODULE_VERSION` |
| Auto-bump PATCH après modification | ✅ DONE **R400-B** (cette session) | `scripts/artcb_bump_module_version.py` |
| Journal append-only historique | ✅ DONE **R400-B** (cette session) | `data/trace/module_version_history.jsonl` |
| Intégration CI/CD (bump auto au commit) | ❌ RESTE | git hook pre-commit ou CI |

### 1.4 Auto-feedback / rétrospective post-tâche

| Élément | État | Fichier |
|---------|------|---------|
| Script rétrospective basé sur faits | ✅ DONE — R392/R394-D | `scripts/artcb_r392_auto_feedback.py` |
| Intégration stop.py | ✅ DONE — R396-A | `.bob/hooks/stop.py:127` |
| FAITS/OBSERVATIONS/RISQUES/LEÇONS/ACTIONS | ✅ DONE | R392 |
| **Section AVANT / APRÈS** | ✅ DONE **R401** (cette session) | R392 v1.2.0 |
| **POINTS FORTS / POINTS FAIBLES** | ✅ DONE **R401** (cette session) | R392 v1.2.0 |
| Parallèle au développement (≠ ARTCB utilisateurs) | ✅ RESPECTÉ | stop.py hors cycle API principal |

### 1.5 Cartographie rules télémétriques par domaine

| Élément | État | Fichier |
|---------|------|---------|
| 230 CR-* avec domain/primary_domain | ✅ DONE — R393/R394E | `rules/rule_corpus_index.json` |
| Domaines : PROTOCOL/GOVERNANCE/LESSONS/NETWORK/TESTING/ROADMAP/IDENTITY | ✅ DONE | Classifié par `artcb_r393_v2` |
| Réorganisation auto selon usage/cas | ⚠️ PARTIEL | La classification existe ; le **routage automatique** (placer une règle au bon endroit) reste à implémenter |
| RT-* REGISTRY (20 règles opérationnelles) | ✅ DONE | `rules/rule_registry.json` |
| Coverage et anti-divergence | ✅ DONE — R375 | `rules/rule_coverage.json` |

### 1.6 Frontend — suppression P2P, Memory IA, etc.

| Élément | État | Commit |
|---------|------|--------|
| Pages /memorize et /agent-memory supprimées | ✅ DONE — R398 | `4df65a4` |
| Nav P2P/Memory supprimée | ✅ DONE — R398/R379 | `4df65a4` |
| 12 fonctions P2P/Pool supprimées de client.ts | ✅ DONE — R398 | `4df65a4` |
| AgentPanel.tsx supprimé | ✅ DONE — R398 | `4df65a4` |
| **Commandes `pool status/prefs/jobs/incoming` Console.tsx** | ✅ DONE **R401** (cette session) | — |
| **Placeholder console avec `pool status | p2p sync`** | ✅ DONE **R401** (cette session) | — (7 langues) |
| Clés orphelines `agent_memory_*` dans type Translations | ✅ DONE **R401** (cette session) | commentées |

### 1.7 Admin reset/revoke device credential

| Élément | État | Fichier |
|---------|------|---------|
| `admin_revoke_by_fingerprint()` | ✅ DONE — R379 | `wallet_device_binding.py:266` |
| `admin_revoke_by_wallet()` | ✅ DONE — R379 | `wallet_device_binding.py:290` |
| Route `DELETE /api/v1/admin/device-binding/fingerprint/{fp}` | ✅ DONE — R379 | `admin_device_binding_routes.py:112` |
| Route `DELETE /api/v1/admin/device-binding/wallet/{name}` | ✅ DONE — R379 | `admin_device_binding_routes.py:150` |
| Trace nanoseconde audit trail | ✅ DONE | `admin_device_binding_routes.py:62` |
| Documenté dans README / guide admin | ❌ RESTE | |

---

## 2. AVANT / APRÈS — R401

### 2.1 `scripts/artcb_r392_auto_feedback.py`

**AVANT (v1.1.0 — R394-D)** :
- Sections : FAITS / OBSERVATIONS / RISQUES / LEÇONS / ACTIONS / Commits
- Pas de section AVANT/APRÈS
- Pas de POINTS FORTS / POINTS FAIBLES

**APRÈS (v1.2.0 — R401)** :
- Ajout section `## AVANT / APRÈS (modifications cette session)` — tableau git diff --stat
- Ajout section `## ✅ POINTS FORTS` — basé sur faits mesurés (tests PASS, versioning, commits)
- Ajout section `## ⚠️ POINTS FAIBLES / À AMÉLIORER` — basé sur faits mesurés (tests FAIL, non mesuré, manque versioning)
- Suppression de la section "Intégration automatique R394-C" (déjà intégrée)

### 2.2 `scripts/artcb_bump_module_version.py` (NOUVEAU — R400-B)

**AVANT** : N'existait pas.

**APRÈS** :
- `scripts/artcb_bump_module_version.py` v1.0.1 (15/15 tests PASS)
- Bump PATCH atomique + journal `data/trace/module_version_history.jsonl`
- Champs : `{timestamp_ns, module, previous_version, new_version, bump, reason, git_sha, sha256_before, sha256_after}`
- Mode bulk `--since <sha>` pour bumper tous les modules modifiés d'un coup

### 2.3 `frontend/src/pages/Console.tsx`

**AVANT (lignes 87-94)** :
```typescript
} else if (trimmed === "pool status") {
  out.push(JSON.stringify(await apiGet("/pool/status"), null, 2));
} else if (trimmed === "pool prefs") { ...
} else if (trimmed === "pool jobs") { ...
} else if (trimmed === "pool incoming") { ...
```

**APRÈS** : Blocs pool supprimés. Placeholder : `help | health | pool status | p2p sync | mining status` → `help | health | mining status | chain | governance` (7 langues)

### 2.4 `frontend/src/i18n/translations.ts`

**AVANT** : `agent_memory_title`, `agent_memory_tab_*` dans le type `Translations` (non commentés)

**APRÈS** : Commentés avec `// Agent Memory Page — supprimé R401 (backend-only)` — le type `Partial<Translations>` garantit la compatibilité

---

## 3. Tests

| Suite | Résultat |
|-------|---------|
| `tests/test_r400b_bump_module_version.py` | 15/15 PASS ✅ |
| `scripts/artcb_r392_auto_feedback.py --since HEAD~1` | Exécution OK ✅ |
| `data/trace/module_version_history.jsonl` | Créé et valide ✅ |

---

## 4. Ce qui RESTE à faire (prochaines sessions)

| Priorité | Tâche | Blocage |
|----------|-------|---------|
| HIGH | TASK-001 : FAR/FRR sur capteurs réels, calibrage seuil Hamming | Capteurs physiques requis |
| HIGH | TASK-006-LIVE-VALIDATION : DV-01/02/06/07 | SSH live N2/N4/N3 |
| MED | Git hook pre-commit pour auto-bump MODULE_VERSION | dev workflow |
| MED | Admin reset — documentation dans README | — |
| LOW | FHE véritable (SEAL/OpenFHE) — après calibrage Hamming | Décision post FAR/FRR |
| LOW | Routage automatique des règles CR-* par domaine | TASK-RULES |

---

*`CERTIFIED_100=false` | Rapport R401 — ne jamais écraser les anciens rapports*
