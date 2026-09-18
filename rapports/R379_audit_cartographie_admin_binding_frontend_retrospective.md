# R379 — Audit cartographie + Admin device-binding + Frontend nettoyage + Règles télémétrie

**Date :** 2026-09-18
**Commit R379 :** `e9cf1a1766fdcc5af3d235f69848e1bb8bb8d2f4` — poussé sur `origin/main` ✅
**Commit L-049 :** `358c27018f5ed2450f23dcbc77b11c9f62c2dba9` — HEAD `origin/main` ✅
**Statut :** ✅ CODE + PUSH confirmés sur origin/main
**Tests locaux :** 7/7 PASS (déclarés dans commit — pas de CI GitHub disponible)
**Déploiement live :** à vérifier séparément (R380)
**CERTIFIED_100 :** false
**Avancement global :** 78%

---

## 1. Contexte

Suite au rapport de l'expert sur R378 (Hamming direct), l'utilisateur a posé 6 questions parallèles :

1. Identifier ce qui est déjà fait vs ce qui reste dans l'audit IA ARTCB + biométrie
2. Log forensic nanoseconde — est-il automatique et exhaustif ?
3. Versioning de chaque fichier après chaque modification
4. Supprimer P2P / mémoire IA du frontend
5. Règle d'auto-feedback / rétrospective après chaque tâche
6. Cartographie des règles télémétriques par catégorie

---

## 2. Audit — Ce qui était déjà FAIT (avant R379)

| Domaine | État | Référence |
|---------|------|-----------|
| Log forensic nanoseconde runtime HTTP | ✅ ACTIF | `src/artcb/trace/ns.py` + middleware `main.py` ligne 159 |
| Logging DEBUG par défaut | ✅ ACTIF | `src/artcb/logging_config.py` `ARTCB_DEBUG=true` |
| JSONL par nœud | ✅ ACTIF | `logs/YYYYMMDD_artcb_startup_<node>.json` |
| Frontend /reflex, /memorize, /logs retirés | ✅ (R359) | `App.tsx` commentaire ligne 1 |
| WalletDeviceBinding anti-fraude | ✅ ACTIF | `wallet_device_binding.py` — HTTP 409 device_wallet_limit |
| Corpus règles 230 CR-* | ✅ (R375) | `rules/rule_corpus_index.json` |
| Biométrie BCH + Hamming | ✅ (R374/R378) | `biometric_onchain.py` |
| Révocation credential WebAuthn | ✅ (R363) | `/identity/device/revoke` |

---

## 3. Ce qui manquait avant R379

| Domaine | Problème |
|---------|----------|
| Admin reset WalletDeviceBinding | ❌ Aucun endpoint — nécessitait manipulation manuelle du JSON |
| Frontend P2P + mémoire IA visible | ❌ `/network` et `/agent-memory` encore dans la nav |
| Règle forensic nanoseconde documentée | ⚠️ Active en runtime mais pas dans rule_sources.json |
| Règle versioning module | ⚠️ Pratique implicite — non formalisée dans rule_sources.json |
| Règle auto-rétrospective | ❌ Absente de rule_sources.json — rétrospectives manuelles seulement |
| Classification CR-* par domaine | ⚠️ Partielle — categories/domain absents de rule_sources.json |

---

## 4. Implémentation R379 — Avant / Après

### 4.1 Admin reset device binding

#### AVANT

**Fichier :** `src/artcb/security/wallet_device_binding.py`  
Dernière ligne : `list_test_bindings()` (ligne 261)  
**Pas de méthode admin. Reset = manipulation manuelle de `data/wallet_device_bindings.json`.**

#### APRÈS

Ajout dans `wallet_device_binding.py` (lignes 264–328) :

```python
# ── R379 — Admin reset/revoke (contrôlé, jamais silencieux) ──────────────
def admin_revoke_by_fingerprint(self, device_fingerprint: str) -> dict | None
def admin_revoke_by_wallet(self, wallet_name: str) -> dict | None
def admin_revoke_test_by_wallet(self, wallet_name: str) -> dict | None
```

Nouveau fichier : `src/api/admin_device_binding_routes.py`

Endpoints créés :
- `GET  /api/v1/admin/device-binding/list` → liste PROD + TEST
- `DELETE /api/v1/admin/device-binding/fingerprint/{fingerprint}` → revoke PROD par fingerprint
- `DELETE /api/v1/admin/device-binding/wallet/{wallet_name}` → revoke PROD par wallet
- `DELETE /api/v1/admin/device-binding/test/wallet/{wallet_name}` → revoke TEST par wallet

Tous protégés par `require_write_actor` (opérateur uniquement).  
Trace nanoseconde `kind=admin_device_binding` émise sur chaque opération.

Enregistré dans `src/api/main.py` ligne 452 :
```python
app.include_router(admin_device_binding_router)
```

**Pour ton cas concret :**
```bash
# Supprimer le binding de ton téléphone (fingerprint 97a0b6403ecb4932…)
DELETE /api/v1/admin/device-binding/fingerprint/97a0b6403ecb4932...
Authorization: Bearer <ton_api_key_operateur>
```

---

### 4.2 Frontend — retrait P2P et mémoire IA

#### AVANT — `frontend/src/App.tsx`

```tsx
import { AgentMemory } from "./pages/AgentMemory";  // ligne 7
import { Network } from "./pages/Network";            // ligne 16
...
<Route path="network" element={<Network />} />        // ligne 46
<Route path="agent-memory" element={<AgentMemory />} /> // ligne 48
```

#### APRÈS — `frontend/src/App.tsx`

```tsx
// R379 — Supprimé du frontend : /agent-memory (P2P IA), /network (P2P pairs + pool ML-KEM)
// Backend AgentMemory, P2P, Network : conservés — agents/API uniquement
// Imports AgentMemory + Network : supprimés
// Routes /network et /agent-memory : supprimées
```

#### AVANT — `frontend/src/layout/DashboardLayout.tsx`

```tsx
{ to: "/network", label: t('nav_network'), icon: "~" },      // ligne 37
{ to: "/agent-memory", label: t('nav_agent_memory'), icon: "AI" }, // ligne 40
```

#### APRÈS — `frontend/src/layout/DashboardLayout.tsx`

Ces deux entrées de navigation **supprimées**. Section SYSTEM réduite à 6 items.

**Invariant : les fichiers backend sont CONSERVÉS :**
- `frontend/src/pages/AgentMemory.tsx` — fichier toujours présent (référençable par agents)
- `frontend/src/pages/Network.tsx` — fichier toujours présent
- `src/api/p2p_routes.py` — backend P2P intact
- `src/api/ai_routes.py` — backend mémoire IA intact

---

### 4.3 Règles télémétriques — ajout 3 sources dans rule_sources.json

#### AVANT : 20 règles actives, registry_version=6, refreshed_by=R375

#### APRÈS : 23 règles actives, registry_version=7, refreshed_by=R379

Trois nouvelles sources ajoutées avec champs `category` et `domain` :

| source_id | category | domain | activation | trigger |
|-----------|----------|--------|------------|---------|
| `forensic_nanosecond` | observability | forensic_logging | automatic | every_http_request + every_block_write |
| `module_versioning` | traceability | versioning | per_commit | every_code_modification |
| `auto_retrospective` | quality_assurance | retrospective | automatic | task_finalized |

---

## 5. Réponses directes aux questions de l'utilisateur

### Q : Les règles du système de log forensic nanoseconde sont-elles toujours activées ?

**Réponse : OUI — automatiquement, sans exception.**

Le middleware `nanosecond_http_trace` dans [`main.py`](src/api/main.py:159) intercepte CHAQUE requête HTTP (mode normal ET bootstrap). Le fichier `trace/ns.jsonl` reçoit : `ts_ns`, `mono_ns`, `pid`, `kind`, `method`, `path`, `dur_ns`, `http`, `ok`.

`ARTCB_DEBUG=true` par défaut dans `logging_config.py` ligne 67.

**Ce qui n'est pas encore couvert :** trace nanoseconde sur les modifications de code elles-mêmes (ex. hook git pre-commit). Cela reste une piste future (hook Bob IDE PostToolUse existe mais n'émet pas vers `trace/ns.jsonl`).

### Q : Versioning de chaque fichier et module

**Réponse : Convention formalisée dans R379.**

Règle ajoutée dans `rule_sources.json` :
- Chaque fichier Python modifié dans un commit R-XXX → docstring ligne 1 mise à jour avec `R-XXX (YYYY-MM-DD)`
- `release.py` expose le `git_sha` comme version runtime du nœud déployé

### Q : Règle d'auto-feedback / rétrospective

**Réponse : Règle formalisée dans R379.**

Règle `auto_retrospective` ajoutée dans `rule_sources.json` :
- Après chaque R-XXX finalisé → rapport `rapports/R-XXX_*.md` obligatoire
- Contenu : points forts, points faibles, avant/après lignes exactes, métriques tests, limites honnêtes
- CERTIFIED_100=false dans chaque rapport
- **Séparation** : rétrospective produite EN PARALLÈLE, jamais à la place du développement

### Q : Cartographie des règles par catégorie

**Réponse : 3 catégories ajoutées dans rule_sources.json.**

Champs `category` et `domain` ajoutés sur les 3 nouvelles sources :
- `observability / forensic_logging`
- `traceability / versioning`
- `quality_assurance / retrospective`

⚠️ Les 18 sources existantes n'ont pas encore ces champs (classification manuelle restante — documentée comme limite dans R375 et maintenue ici).

### Q : Supprimer P2P et mémoire IA du frontend

**Réponse : FAIT.**

`/network` et `/agent-memory` retirés de la nav et des routes React. Backend conservé intégralement.

---

## 6. Audit langage IA ARTCB — ce qui est fait / ce qui reste

### Fait

| Module | Fonction d'analyse |
|--------|--------------------|
| `src/artcb/ir/encoder.py` | Texte → graphe de concepts (nœuds typés) |
| `src/artcb/ir/decoder.py` | Graphe → texte reconstruit |
| `src/artcb/ir/rules.py` | Évaluation règles conditionnelles (smart contracts) |
| `src/artcb/ir/grammar.py` | Grammaire symbolique ARTCB |
| `src/artcb/ir/concept.py` | Modèle de concept : entité, relation, attribut |
| `src/artcb/ir/llm_encoder.py` | Path B LLM (Bob) — enrichissement sémantique |
| `src/artcb/memory/vector_store.py` | Recherche vectorielle sémantique |
| `src/artcb/memory/concept_network.py` | Réseau de concepts inter-liés |
| `src/artcb/kcg/` | Knowledge Concept Graph — comparaison croisée |
| Dual-path A+B | Rule-based + LLM — les deux actifs simultanément |

### Reste à faire (non audité formellement)

- Cartographie exhaustive des types d'analyse croisée (intersections de concepts, distance sémantique entre blocs)
- Benchmark comparatif des deux paths A vs B sur les mêmes entrées
- Rapport de couverture du langage ARTCB IR par domaine sémantique

---

## 7. Points forts / points faibles (rétrospective R379)

### Points forts

- Reset device binding implémenté proprement sans désactiver la protection globale
- Trace nanoseconde sur chaque opération admin — audit trail complet
- Frontend allégé : 2 pages backend-only retirées de la surface publique
- Règles formalisées dans rule_sources.json avec champs category/domain structurés

### Points faibles

- La classification category/domain n'est pas encore appliquée aux 18 sources existantes
- Le versioning de module (docstring R-XXX) n'est pas encore un hook automatique git
- L'auto-rétrospective n'est pas encore déclenchée automatiquement par un hook Bob IDE
- Le log forensic ns ne couvre pas les modifications de code elles-mêmes (uniquement runtime HTTP)

---

## 8. Tests requis (à jouer avant mainnet)

- `DELETE /api/v1/admin/device-binding/fingerprint/97a0b6403ecb4932` → 200 OK
- Recréation wallet sur le même appareil → OK (binding supprimé)
- Tentative sans Bearer opérateur → 401/403
- `GET /api/v1/admin/device-binding/list` → liste correcte PROD + TEST
- Build frontend `npm run build` → pas d'import manquant

**CERTIFIED_100 = false**
