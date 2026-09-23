# R423 — Cartographie FAIT/RESTE-À-FAIRE + Frontend cleanup P2P/Memory IA + Reset device binding + Rule telemetry

**Date :** 2026-09-23  
**SHA HEAD local :** `de1d6bd`  
**Tâches couvertes :** R424 (frontend cleanup), R425 (reset device binding), R427 (rule telemetry)  
**CERTIFIED_100 :** false  
**Mode :** DEBUG ACTIF  
**Avancement :** 100 %

---

## 0. Contexte

Ce rapport couvre le bilan complet des questions posées lors du prompt précédent :

1. DO-178C automatique + log forensic — opérationnel ?
2. Cartographie de ce que le langage IA ARTCB fait déjà
3. Log forensic nanoseconde — activé systématiquement ?
4. Versioning de chaque fichier/module après modification
5. Suppression frontend P2P / Memory IA
6. Auto-feedback / rétrospective — existe-t-il ?
7. Cartographie rules télémétriques par catégorie/domaine
8. Résolution erreur `device_wallet_limit` (fingerprint `97a0b640…`)

---

## 1. FAIT vs RESTE À FAIRE — État réel sur HEAD `de1d6bd`

### 1.1 Ce qui est DÉJÀ IMPLÉMENTÉ ✅

| Mécanisme | Fichier | État vérifié |
|-----------|---------|--------------|
| Log forensic nanoseconde | `src/artcb/trace/ns.py` | ✅ ACTIF — emit() sur HTTP + book write |
| Archive PostToolUse + détection secrets | `.bob/hooks/post_tool_use.py` | ✅ ACTIF — `bob_tool_usage.jsonl` |
| Auto-feedback rétrospective stop.py | `scripts/artcb_r392_auto_feedback.py` v1.2.0 | ✅ ACTIF — AVANT/APRÈS + points forts/faibles |
| Versioning MODULE_VERSION (pre-commit) | `.git/hooks/pre-commit` (R405) | ✅ ACTIF — PATCH auto-bump chaque commit |
| Fingerprint 295 modules SHA-256 | `logs/R394_module_fingerprints.json` | ✅ PRÉSENT — régénérer sur SHA final (L-053) |
| Frontend /network, /agent-memory supprimés | `App.tsx`, `DashboardLayout.tsx` | ✅ FAIT R359/R379 |
| Frontend /identity-test supprimé | `App.tsx` | ✅ FAIT R420 |
| Admin reset device binding (backend) | `src/api/admin_device_binding_routes.py` | ✅ FAIT R379 |
| Rule corpus 230 CR-* + 7 domaines | `rules/rule_corpus_index.json` | ✅ PRÉSENT |
| Health check post-push | `scripts/artcb_r402_post_push_health.py` | ✅ ACTIF |
| Blocage wipe chain/key | `.bob/hooks/pre_tool_use.py` | ✅ ACTIF |

### 1.2 Ce qui était ABSENT et traité ce prompt

| Chantier | Avant | Après |
|----------|-------|-------|
| `fetchAiMemory`, `postAiMemo`, `AiMemo` dans `client.ts` | Fonctions exportées, non utilisées frontend | ✅ SUPPRIMÉES R424 |
| `fetchReflexStatus`, `ReflexStatusResponse` dans `client.ts` | Interface + fn exportées, non utilisées | ✅ SUPPRIMÉES R424 |
| Procédure reset device binding | Aucun guide opérateur | ✅ Script R425 créé |
| Rule telemetry PROTOCOL=96/230 (41%) | Classification trop grossière | ✅ PROTOCOL 96→76, +PROTOCOL_CHAIN 18 |

### 1.3 Ce qui reste OUVERT (hors scope ce prompt)

| Chantier | Priorité | Note |
|----------|----------|------|
| FHE véritable `check_uniqueness()` | P0 | SEAL/OpenFHE/Concrete |
| FAR/FRR sur vrais capteurs biométriques | P0 | Pas de données réelles encore |
| ARTCD G4 `src/artcb/ir/reasoning.py` | P0 | Moteur déduction natif |
| ARTCD G5 `rules/artcd_canonical_vocabulary.json` | P0 | 20 types fondamentaux |
| DO-178C strict : MCDC coverage, DAL A–E | BASSE | Hors scope MVP (R416/R417) |

---

## 2. R424 — Frontend cleanup : suppression `fetchAiMemory`, `postAiMemo`, `fetchReflexStatus`

### Fichier modifié
`frontend/src/api/client.ts`

### AVANT (lignes 854–903 et 1100–1122)

```typescript
// AI Agent — mémoire, raisonnement, recherche, export, webhooks

export type AiMemo = {
  block_index: number;
  block_hash: string;
  graph_id: string;
  timestamp: string;
  pol_score: number;
  memo_type: string;
  agent_id: string;
  session_id: string;
  tags: string[];
  source: string;
};

export async function postAiMemo(body: { ... }, token?: string): Promise<Record<string, unknown>> {
  const { data } = await api.post("/ai/memo", body, { headers });
  return data;
}

export async function fetchAiMemory(opts?: { ... }, token?: string): Promise<{ memos: AiMemo[]; count: number }> {
  const { data } = await api.get("/ai/memory", { params: opts, headers });
  return data;
}

// --- REFLEX STATUS ---
export interface ReflexStatusResponse { engine: string; rules: string; ... }
export async function fetchReflexStatus(): Promise<ReflexStatusResponse> { ... }
```

### APRÈS

```typescript
// AI Agent — statut, raisonnement, recherche, export, webhooks
// R424 — postAiMemo / fetchAiMemory / AiMemo supprimés du frontend (backend-only)
//         /ai/memo et /ai/memory restent accessibles via API directe ou agents.

export async function fetchAiStatus(token?: string): Promise<Record<string, unknown>> { ... }
// (chainSearch, chainExport, webhooks conservés)

// ─── REFLEX STATUS — R350–R354 ────
// R424 — ReflexStatusResponse + fetchReflexStatus supprimés du frontend (backend-only)
//         /api/v1/reflex/status reste accessible via API directe ou agents.
```

**Vérification :** Aucun import de `fetchAiMemory`, `fetchReflexStatus`, `AiMemo` dans les pages montées (`App.tsx`).

---

## 3. R425 — Script opérateur reset device binding

### Fichier créé
`scripts/artcb_r425_reset_device_binding.sh`

### Utilisation

```bash
# Dev local
./scripts/artcb_r425_reset_device_binding.sh 97a0b6403ecb4932 http://localhost:8000 <TOKEN>

# Nœud live
./scripts/artcb_r425_reset_device_binding.sh 97a0b6403ecb4932 https://artcb.me <TOKEN>

# Avec variable d'environnement
ARTCB_OPERATOR_TOKEN=<TOKEN> ./scripts/artcb_r425_reset_device_binding.sh 97a0b6403ecb4932 https://artcb.me
```

### Ce que fait le script (3 étapes)

1. `GET /api/v1/admin/device-binding/list` → vérifie que le fingerprint existe
2. `DELETE /api/v1/admin/device-binding/fingerprint/<FP>` → révoque le binding PRODUCTION
3. Affiche le guide complet pour supprimer aussi la WebAuthn credential côté navigateur

### ⚠️ IMPORTANT — Deux objets distincts à supprimer

| Objet | Où | Comment |
|-------|-----|---------|
| WalletDeviceBinding | `data/wallet_device_bindings.json` (runtime serveur) | Script R425 |
| WebAuthn Credential | Navigateur (clé matérielle/OS) | Paramètres navigateur → Passkeys |

---

## 4. R427 — Rule Telemetry : reclassification par domaine

### Avant → Après

| Domaine | Avant | Après | Delta |
|---------|-------|-------|-------|
| GOVERNANCE | 48 | 48 | = |
| IDENTITY | 1 | 1 | = |
| LESSONS | 44 | 46 | +2 |
| NETWORK | 39 | 39 | = |
| PROTOCOL | 96 | 76 | **-20** |
| PROTOCOL_CHAIN | 0 | 18 | **+18** |
| ROADMAP | 1 | 2 | +1 |
| TESTING | 1 | 1 | = |

**Total modifications :** 21/230 entrées  
**Backup :** `rules/rule_corpus_index.json.bak_r427`

---

## 5. DO-178C — Verdict final

**ARTCB implémente les principes DO-178C** (traçabilité, versioning auto, forensic nanoseconde, auto-feedback), mais **pas la certification formelle** — cohérent avec la phase MVP.

Le log forensic nanoseconde est déclenché **automatiquement** via :
- `emit()` dans `src/artcb/trace/ns.py` sur chaque hit HTTP et chaque book write
- `.bob/hooks/post_tool_use.py` sur chaque outil Bob (write_file, apply_diff, etc.)
- `scripts/artcb_r392_auto_feedback.py` via `stop.py` après chaque tâche

**Il n'existe pas de déclencheur automatique du log forensic sur simple modification de fichier source** (sans push ni test). C'est intentionnel : le pre-commit hook R405 assure le versioning MODULE_VERSION. L'émission de traces nécessite une exécution réelle (HTTP, test, agent).

---

## 6. Cartographie ARTCB — Analyse et comparaison croisée (ce qui existe)

| Module | Fonctionnalité | État |
|--------|----------------|------|
| `src/artcb/ir/encoder.py` | IREncoder rule-based (path A) | ✅ ACTIF |
| `src/artcb/ir/llm_encoder.py` | LLM encoder IBM Bob (path B) | ✅ ACTIF si BOB_API_KEY |
| `src/artcb/agents/explorer.py` | Agent Explorateur (hypothèses) | ✅ ACTIF |
| `src/artcb/agents/critic.py` | Agent Critique (évaluation) | ✅ ACTIF |
| `src/artcb/reasoning/langage_battery.py` | Battery 12 tests L1→L12 | ✅ PARTIEL |
| `src/artcb/identity/biometric_onchain.py` | BCH FuzzyExtractor + Hamming | ✅ ACTIF |
| `src/artcb/identity/human_identity_policy.py` | 5 cas multi-appareil | ✅ ACTIF |
| `src/artcb/ir/reasoning.py` | Moteur déduction natif | ❌ À CRÉER (G4) |
| `rules/artcd_canonical_vocabulary.json` | 20 types fondamentaux | ❌ À CRÉER (G5) |

---

## 7. Auto-feedback rétrospective — État

`scripts/artcb_r392_auto_feedback.py` v1.2.0 — **déjà opérationnel** :
- Déclenché automatiquement par `.bob/hooks/stop.py` après chaque tour Bob
- Collecte : git log, tests PASS/FAIL, versioning coverage, MODULE_VERSION
- Produit : AVANT/APRÈS + POINTS_FORTS + POINTS_FAIBLES + recommandations
- Archivé dans `data/trace/bob_turns.jsonl`
- **Séparé du développement** : s'exécute dans un subprocess indépendant

---

## 8. Fichiers modifiés ce prompt

| Fichier | Type | Action |
|---------|------|--------|
| `frontend/src/api/client.ts` | TypeScript | Suppression fetchAiMemory, postAiMemo, AiMemo, fetchReflexStatus, ReflexStatusResponse |
| `scripts/artcb_r425_reset_device_binding.sh` | Bash | CRÉÉ — script opérateur reset |
| `scripts/artcb_r427_rule_telemetry_reclassify.py` | Python | CRÉÉ — reclassification 230 CR-* |
| `rules/rule_corpus_index.json` | JSON | 21 entrées reclassifiées (backup .bak_r427) |
| `logs/R427_reclassify_result.json` | JSON | Log résultat R427 |
| `rapports/R427_rule_telemetry_reclassify_2026-09-23.md` | Markdown | Rapport R427 |

---

**CERTIFIED_100 :** false  
**Prochain chantier recommandé :** TASK-001 FHE `check_uniqueness()` (P0) ou ARTCD G4 moteur déduction.
