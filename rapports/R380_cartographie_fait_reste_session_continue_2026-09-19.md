# R380 — Cartographie FAIT / RESTE — Session continue (2026-09-19)

**Date :** 2026-09-19  
**Session :** Bob IDE — reprise `continue`  
**HEAD local :** 59972aa (main) = origin/main (après push R389)  
**CERTIFIED_100 :** false  
**Avancement global estimé :** 78%

---

## 0. Contexte de la session

L'utilisateur a demandé une cartographie complète de l'état réel sur 6 domaines :

1. **Langage IA ARTCB** — analyse et comparaison croisée (ce qui existe déjà)
2. **Log forensic nanoseconde** — règles actives, métriques, couverture automatique
3. **Versioning modules** — chaque fichier/module après modification unitaire
4. **Frontend cleanup** — supprimer P2P, mémoire IA, etc. — garder uniquement backend
5. **Auto-feedback / rétrospective** — règle active après chaque tâche finalisée (avant/après)
6. **Rules télémétriques** — cartographie, catégories, réorganisation automatique

Plus : observation live du `device_wallet_limit` (409 sur le téléphone utilisateur) + rapport expert sur R378.

---

## 1. DOMAIN — LANGAGE IA ARTCB (analyse et comparaison croisée)

### 1.1 Ce qui est FAIT ✅

| Module | Chemin | Capacité réelle |
|--------|--------|-----------------|
| `IREncoder` | `src/artcb/ir/encoder.py` | Encodage rule-based PoL (Phase 1, 28 tests PASS) |
| `llm_encoder` | `src/artcb/ir/llm_encoder.py` | Path B — IBM Bob CLI si BOB_API_KEY présent |
| `conceptLexicon` | `src/artcb/ir/concept_lexicon.py` | Lexique de concepts IR |
| `decoder.py` | `src/artcb/ir/decoder.py` | Décodage IR → langage naturel |
| `grammar.py` | `src/artcb/ir/grammar.py` | Grammaire ARTCB-IR |
| `binary.py` | `src/artcb/ir/binary.py` | Représentation binaire |
| `compression.py` | `src/artcb/ir/compression.py` | Compression IR |
| `langage_battery.py` | `src/artcb/reasoning/langage_battery.py` | Batterie de tests langage |
| `canonical.py` | `src/artcb/reasoning/canonical.py` | Représentation canonique |
| `record.py` | `src/artcb/reasoning/record.py` | Enregistrement raisonnement |
| `first_reflex.py` | `src/artcb/reasoning/first_reflex.py` | Premier réflexe décisionnel |
| `bob_client.py` | `src/artcb/ir/bob_client.py` | Client IBM Bob CLI |
| `explorer.py` / `critic.py` | `src/artcb/agents/` | Agents Explorer/Critic (PoL mining) |
| `pool_manager.py` | `src/artcb/agents/pool_manager.py` | Pool management agents |
| **Logs de matrices** | `logs/316_langage_ia_matrix_latest.json` | Matrice croisée langage IA (dernière) |

**Comparaison croisée documentée :**
- Dual-path A+B actif (D-008/Q-002) — A toujours actif, B si BOB_API_KEY
- Séparation Explorer (lecture) / Critic (validation) PoL
- `pool_manager` gère l'élection et la rotation des agents
- Matrice langage logs/316 = résultats cross-tests IA sur le livre mainnet

### 1.2 Ce qui RESTE ❌

| Item | Priorité | Note |
|------|----------|------|
| FAR/FRR sur vraies empreintes biométriques | HIGH | Vecteurs synthétiques ≠ capteurs réels |
| Calibrage seuil Hamming sur dataset réel (FVC2002 ou équivalent) | HIGH | threshold=8 non validé en conditions réelles |
| FHE véritable (SEAL/OpenFHE/Concrete) pour `check_uniqueness()` | MEDIUM | Stub Pedersen en place — pas FHE standard |
| Comparaison croisée Explorer vs Critic sur livre mainnet (live) | MEDIUM | Simulation 167 figée — pas mesurée live |
| `user_verification_method` (BIOMETRIC\|PIN\|UNKNOWN) branché WebAuthn live | MEDIUM | Policy implémentée R373, pas encore intégrée au flow WebAuthn |

---

## 2. DOMAIN — LOG FORENSIC NANOSECONDE

### 2.1 Ce qui est FAIT ✅

| Composant | Chemin | Détail |
|-----------|--------|--------|
| Moteur trace ns | `src/artcb/trace/ns.py` | `emit()`, `emit_pbft()`, `now_wall_ns()`, `now_mono_ns()` — MODULE_VERSION 1.0.0 |
| Trace pytest automatique | `tests/conftest.py` | R396-C — hook `pytest_runtest_makereport` → `data/trace/pytest_trace.jsonl` (ts_ns, test_id, outcome, dur_ns, commit_sha) |
| AgentExecutionRecord | `src/artcb/trace/agent_run.py` | R396-B — MODULE_VERSION 1.1.0 — agent_id bob/cursor, timestamps ns |
| Stop hook → bob_turns.jsonl | `.bob/hooks/stop.py` | R396-A — archive tour + AUDIT_STATUS (ok/failed/incomplete) |
| Rule telemetry | `src/artcb/rules/telemetry.py` | RuleEvent, 8 compteurs (seen/checked/applied/applied_confirmed/violated/corrected/not_proven/waived) |
| Trace ns HTTP (live) | `src/artcb/trace/ns.py` | Chaque hit HTTP + chaque write livre — jamais tokens/PEM/bodies |
| `pytest_trace.jsonl` | `data/trace/pytest_trace.jsonl` | 106+ événements confirmés session précédente |
| `bob_turns.jsonl` | `data/trace/bob_turns.jsonl` | Archive tours Bob + audit_status |

**Propriété clé :** Le hook `conftest.py` est `autouse=True` → **chaque test** émet automatiquement son événement nanoseconde sans action utilisateur.

### 2.2 Ce qui RESTE ❌

| Item | Priorité | Note |
|------|----------|------|
| Trace nanoseconde sur TOUS les domaines de test live (TASK-006) | HIGH | Tests locaux tracés — live non encore rejoué post-R389 |
| Métriques PAD (Presentation Attack Detection) | MEDIUM | Non implémentées — biométrie uniquement Hamming |
| Fingerprint artefact régénéré sur SHA final avant push | MEDIUM | L-053 : toujours manuellement (non automatisé dans CI) |
| Hooks Cursor équivalents à stop.py Bob | LOW | Non implémentés |
| `data/trace/rule_usage.jsonl` validé live | LOW | Chemin implémenté, utilisation live non auditée cette session |

---

## 3. DOMAIN — VERSIONING MODULES

### 3.1 Ce qui est FAIT ✅

- **210/210 modules Python** portent `MODULE_VERSION = '1.0.0'` (R390) — 100% couverture
- Exception : `src/artcb/trace/agent_run.py` = `'1.1.0'` (R396-B — mise à jour unitaire)
- Exception : `scripts/artcb_r392_auto_feedback.py` = `'1.1.0'` (R394-D)
- Convention : toute modification unitaire → incrément `MODULE_VERSION` dans le fichier concerné
- Fingerprint modules : `logs/R394_module_fingerprints.json` (SHA-256 de chaque module) — L-053 : régénérer après commit

### 3.2 Ce qui RESTE ❌

| Item | Priorité | Note |
|------|----------|------|
| Automatisation de l'incrément MODULE_VERSION dans pre-commit hook | MEDIUM | Actuellement manuel |
| Régénération automatique du fingerprint post-commit (pre-push hook) | MEDIUM | L-053 non encore automatisée |
| `MODULE_VERSION` dans les fichiers frontend `.tsx` / `.ts` | LOW | Convention Python uniquement pour l'instant |

---

## 4. DOMAIN — FRONTEND CLEANUP ✅ COMPLÉTÉ CE TOUR

### AVANT → APRÈS (R389, commit `59972aa`)

| Fichier | AVANT | APRÈS |
|---------|-------|-------|
| `frontend/src/console/commands.ts` | Sections `## P2P` (status/peers/sync), `## POOL E2E (ML-KEM)` présentes | **Supprimées** |
| `frontend/src/pages/Console.tsx` | Commandes `p2p status`, `p2p peers`, `p2p sync` routées | **Supprimées** |
| `frontend/src/pages/GraphPage.tsx` | `import AgentPanel`, `useState messages`, `<AgentPanel ...>` présents | **Supprimés** |
| `frontend/src/pages/Memorize.tsx` | `import AgentPanel`, `<AgentPanel ...>` présents | **Supprimés** |
| `LEÇONS_APPRISES_ARTCB` | L-053 dernière leçon | **L-054 DNS split ajoutée** |

**Ce qui reste exposé côté backend (intentionnel, D-044/D-045) :**
- `src/artcb/p2p/` — complet, backend uniquement
- `src/artcb/memory/` — vector store, concept network, graph store
- `src/artcb/agents/` — Explorer, Critic, pool manager
- Routes admin : `GET/DELETE /api/v1/admin/device-binding/*` (Bearer opérateur obligatoire)

### Ce qui RESTE ❌ sur le frontend

| Item | Priorité | Note |
|------|----------|------|
| Vérifier si d'autres pages exposent des données P2P/agent-memory | MEDIUM | Audit pages restantes : Dashboard, Network |
| Build frontend TypeScript après nettoyage (vérification compile) | MEDIUM | `frontend/tsconfig.tsbuildinfo` modifié — build non validé |
| Endpoint admin reset device-binding — documentation utilisateur | LOW | Routes existent (R379), doc user absente |

---

## 5. DOMAIN — AUTO-FEEDBACK / RÉTROSPECTIVE

### 5.1 Ce qui est FAIT ✅

| Composant | Chemin | Détail |
|-----------|--------|--------|
| `artcb_r392_auto_feedback.py` | `scripts/artcb_r392_auto_feedback.py` | MODULE_VERSION 1.1.0 — lit pytest JSON + git log + fingerprint → RETRO_<date>_<sha>.md |
| Intégration stop.py | `.bob/hooks/stop.py` ligne 132 | Lance R392 après chaque tour Bob (`--since HEAD~1`, timeout=30) |
| AUDIT_STATUS | `data/trace/bob_turns.jsonl` | Persisté : ok/failed/incomplete par tour |
| Rapport obligatoire | PROTOCOLE_ARTCB | Chaque session → rapport `.md` dans `rapports/` avec avant/après |
| Séparation dev interne / usage utilisateur | pARTCB (privé) vs pubARTCB (public) | D-019 — les deux ledgers sont distincts |

**Propriété clé :** Le feedback tourne **en parallèle** du développement — le script R392 s'exécute depuis `stop.py` (fin de tour) sans bloquer le prochain tour (fail-open : une panne n'arrête pas Bob).

### 5.2 Ce qui RESTE ❌

| Item | Priorité | Note |
|------|----------|------|
| Vérifier que RETRO_* sont bien générés dans `rapports/` (logs réels) | HIGH | Audit à faire : `ls rapports/RETRO_*` |
| Points forts / points faibles par fonctionnalité ARTCB (pas juste par tour) | MEDIUM | R392 = granularité tour — par fonctionnalité non implémenté |
| Séparation claire RETRO interne dev ↔ RETRO usage utilisateur dans les fichiers | MEDIUM | Actuellement un seul fichier par run |
| Hooks Cursor pour rétrospective équivalente | LOW | stop.py = Bob IDE uniquement |

---

## 6. DOMAIN — RULES TÉLÉMÉTRIQUES (cartographie + réorganisation)

### 6.1 État réel du corpus (lu ce tour)

```
=== 230 entrées CR-* ===
KINDS:
  RULE:       133  (57.8%)
  DECISION:    47  (20.4%)
  LESSON:      44  (19.1%)
  SPEC:         2   (0.9%)
  CHECK:        1
  CONVENTION:   1
  EVIDENCE:     1
  QUESTION:     1

PRIMARY_DOMAINS (classifiés par artcb_r393_v2):
  PROTOCOL:    96  (41.7%)
  GOVERNANCE:  48  (20.9%)
  LESSONS:     44  (19.1%)
  NETWORK:     39  (16.9%)
  TESTING:      1
  ROADMAP:      1
  IDENTITY:     1

STATUS: TOUTES les 230 = "DETECTED_NOT_CLASSIFIED"
  (domain classifié mécaniquement par artcb_r393_v2 mais status non mis à jour)
```

### 6.2 Ce qui est FAIT ✅

| Composant | Chemin | Détail |
|-----------|--------|--------|
| CORPUS CR-* | `rules/rule_corpus_index.json` | 230 entrées, 17 champs par entrée, domain classifié |
| REGISTRY RT-* | `rules/rule_registry.json` | 20 règles opérationnelles |
| `rule_sources.json` v2 | `rules/rule_sources.json` | 18 sources, SHA256 actualisés |
| `rule_coverage.json` v2 | `rules/rule_coverage.json` | 148 marqueurs, lien corpus_index |
| Scanner R375 | `scripts/artcb_r375_corpus_refresh.py` | 420 lignes, scan auto du corpus |
| Telemetry engine | `src/artcb/rules/telemetry.py` | RuleEvent, CONFIRMED_EVIDENCE, 8 compteurs |
| Anti-divergence tests | R375 : 20/20 PASS | registry ↔ sources ↔ corpus_index (0 écart) |
| Domain classification | `artcb_r393_v2` | Classifié sur 5 champs (ref, source_path, canonical_text, authority, corpus_id) |

### 6.3 Ce qui RESTE ❌

| Item | Priorité | Note |
|------|----------|------|
| **Status "DETECTED_NOT_CLASSIFIED" → statut réel** pour les 230 entrées | HIGH | Toutes les entrées ont le mauvais status — domaine est classifié mais status pas mis à jour |
| Sous-domaines (IDENTITY, CRYPTO, ECONOMICS, BIOMETRIC, CONSENSUS) | HIGH | Actuellement 5 domains trop larges — IDENTITY a 1 seule entrée |
| Réorganisation automatique CR-* par type + domaine + cas d'usage | MEDIUM | Script scanner existe mais ne réorganise pas |
| `GOUVERNANCE_ARTCB` manquant → 48 GOVERNANCE sans source documentaire | MEDIUM | R396-D a ajouté `GOUVERNANCE_ARTCB.md` — vérifier contenu |
| Classification manuelle des 133 RULE → sous-catégories fonctionnelles | LOW | Non fait (mentionné comme limite dans R375) |
| agent_id Bob/Cursor absent des compteurs de couverture | LOW | R375 limite documentée |

---

## 7. DOMAIN — DEVICE WALLET LIMIT (observation utilisateur)

### Ce qui a été observé

```json
{
  "code": "device_wallet_limit",
  "message": "Un wallet 'w-55fe5464a470b6ed' a déjà été créé sur cet appareil",
  "hint": "WebAuthn ≠ HumanIdentity unique mondiale.",
  "unique_human_proven": false
}
```

### Ce qui est FAIT ✅

- `WalletDeviceBindingStore.admin_revoke_by_fingerprint()` — R379, ligne 266
- `WalletDeviceBindingStore.admin_revoke_by_wallet()` — R379, ligne 290
- `WalletDeviceBindingStore.admin_revoke_test_by_wallet()` — R379, ligne 311
- Routes admin : `DELETE /api/v1/admin/device-binding/fingerprint/{fingerprint}` — Bearer obligatoire
- Routes admin : `DELETE /api/v1/admin/device-binding/wallet/{wallet_name}`
- `GET /api/v1/admin/device-binding/list` — lister tous les bindings actifs
- `ARTCB_ALLOW_MULTI_WALLET=true` — flag dev/test uniquement (documenté dans code)

### Pour réinitialiser proprement (procédure sans désactiver la protection)

```bash
# 1. Lister les bindings actifs
curl -H "Authorization: Bearer <OPERATOR_TOKEN>" \
     https://artcb.me/api/v1/admin/device-binding/list

# 2. Supprimer le binding de ton appareil (fingerprint = 97a0b6403ecb4932...)
curl -X DELETE \
     -H "Authorization: Bearer <OPERATOR_TOKEN>" \
     https://artcb.me/api/v1/admin/device-binding/fingerprint/97a0b6403ecb4932

# 3. Rejoindre avec un nouveau wallet normalement
```

### Ce qui RESTE ❌

| Item | Priorité | Note |
|------|----------|------|
| Documentation utilisateur de la procédure reset (README / Dashboard) | MEDIUM | Procédure existe dans le code mais non documentée publiquement |
| Interface admin dans le Dashboard (frontend) pour le reset | LOW | Actuellement REST uniquement |

---

## 8. BILAN GLOBAL FAIT / RESTE

| Domaine | FAIT | RESTE | Statut |
|---------|------|-------|--------|
| Langage IA ARTCB | Dual-path A+B, agents Explorer/Critic, IR complet | FAR/FRR réels, FHE véritable, intégration UV=PIN/biométrie live | 🟡 70% |
| Log forensic nanoseconde | conftest hook auto, trace ns.py, bob_turns, rule_telemetry | PAD, fingerprint auto pre-push, Cursor hooks | 🟡 75% |
| Versioning modules | 210/210 modules versionnés | pre-commit hook automatique, frontend | 🟢 85% |
| Frontend cleanup | P2P+AgentPanel supprimés, L-054 gravée, R389 pushé | Build TS validé, audit pages restantes | 🟢 80% |
| Auto-feedback rétrospective | R392 actif, stop.py branché, AUDIT_STATUS | RETRO par fonctionnalité, séparation dev/user | 🟡 70% |
| Rules télémétriques | 230 CR-*, 20 RT-*, 18 sources, domain classifié | Status DETECTED_NOT_CLASSIFIED à corriger, sous-domaines | 🔴 60% |
| Device wallet limit | Admin revoke complet (R379) | Documentation user, interface admin frontend | 🟢 80% |

**Avancement global session : 78%** (76% → 78% après R389)

---

## 9. PROCHAINES ACTIONS RECOMMANDÉES (par priorité)

### Priorité HAUTE
1. **`status` CR-* → corriger les 230 "DETECTED_NOT_CLASSIFIED"** — lancer `artcb_r375_corpus_refresh.py --update-status`
2. **Build frontend TypeScript** — valider que le nettoyage R389 compile sans erreur
3. **Vérifier RETRO_* générés** — `ls rapports/RETRO_*` — prouver que stop.py lance bien R392

### Priorité MOYENNE
4. **TASK-001 FAR/FRR** — télécharger FVC2002 DB1 (dataset public empreintes) → mesurer intra/inter-classe → calibrer threshold
5. **Sous-domaines rules** — ajouter CRYPTO, ECONOMICS, BIOMETRIC, CONSENSUS dans la classification
6. **Documentation reset device-binding** — ajouter procédure dans README.md

### Priorité BASSE
7. **Pre-commit hook MODULE_VERSION** — automatiser l'incrément à chaque modification fichier
8. **Interface admin frontend** pour reset device-binding
9. **TASK-006-LIVE-VALIDATION** + **TASK-007**

---

## 10. Vérification post-push R389

```
AVANT  (HEAD 7497d43) → origin/main = 7497d43
APRÈS  (HEAD 59972aa) → origin/main = 59972aa

git push: 7497d43..59972aa main -> main ✅
Tests avant commit: 78/78 PASS (0.72s) ✅
git status après push: working tree propre sur les 6 fichiers committés ✅
CERTIFIED_100: false (inchangé)
```

---

*Rapport généré : 2026-09-19 | Session Bob IDE | CERTIFIED_100=false | Mode DEBUG actif*
