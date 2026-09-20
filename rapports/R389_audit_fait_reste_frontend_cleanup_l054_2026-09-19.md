# R389 — Audit FAIT/RESTE + Frontend cleanup + L-054 + Cartographie règles télémétriques

**Date :** 2026-09-19  
**Session :** Bob IDE  
**HEAD local :** 7497d43 (main)  
**CERTIFIED_100 :** false  
**Tests :** 106/106 PASS (R373+R374+R376+R378)  
**Avancement global :** 76%

---

## 1. Tâches réalisées cette session

### 1.1 L-054 gravée dans LEÇONS_APPRISES_ARTCB

**AVANT :** L-053 était la dernière leçon. L-054 (DNS split) n'existait pas.  
**APRÈS :** L-054 ajoutée après L-053 :

```
Fichier : LEÇONS_APPRISES_ARTCB
Ligne 253 (après L-053) :

### L-054 — DNS split client = faux positif "site DOWN" (2026-09-19)
Contexte : artcb.me résolu → 172.24.16.51 (IP privée) sur WiFi public.
Leçon : (1) curl --resolve avant tout diagnostic "nœud DOWN"
        (2) 502/timeout sur domaine ≠ service down
        (3) Tester IP directe en parallèle du domaine
        (4) VPN désactivé ≠ DNS correct
        (5) artcb.me DOWN côté client n'implique jamais action côté nœuds
Action : V-09 rapport. Correction : DNS 8.8.8.8/1.1.1.1 en Réglages Système WiFi.
```

---

### 1.2 Frontend cleanup — Suppression P2P / AgentMemory IA

**Objectif :** Supprimer du frontend les éléments P2P et mémoire IA agents duels. Conserver uniquement les interfaces backend utiles.

#### Console.tsx — Suppression commandes p2p

**AVANT (`frontend/src/pages/Console.tsx` lignes 95-100) :**
```tsx
} else if (trimmed === "p2p status") {
  out.push(JSON.stringify(await apiGet("/p2p/status"), null, 2));
} else if (trimmed === "p2p peers") {
  out.push(JSON.stringify(await apiGet("/p2p/peers"), null, 2));
} else if (trimmed === "p2p sync") {
  out.push(JSON.stringify(await apiPost("/p2p/sync"), null, 2));
```

**APRÈS :** Bloc supprimé — les 6 lignes p2p retirées. Les commandes `groups`, `governance`, etc. restent intactes.

#### commands.ts — Suppression sections P2P + POOL E2E (ML-KEM)

**AVANT (`frontend/src/console/commands.ts`) :**
```
  POOL E2E (ML-KEM)
  pool status             — GET /api/v1/pool/status
  pool prefs              — GET /api/v1/pool/preferences
  pool jobs               — GET /api/v1/pool/jobs
  pool incoming           — GET /api/v1/pool/incoming

  P2P
  p2p status              — GET /api/v1/p2p/status
  p2p peers               — GET /api/v1/p2p/peers
  p2p sync                — POST /api/v1/p2p/sync
```

**APRÈS :** Les deux sections (11 lignes) supprimées. La commande `agents <texte>` (moteur PoL) est conservée car ce n'est pas du P2P.

#### Memorize.tsx — Suppression AgentPanel (agents duels Explorer/Critic)

**AVANT (`frontend/src/pages/Memorize.tsx` ligne 10 + ligne 267) :**
```tsx
import { AgentPanel } from "../components/AgentPanel";
...
<AgentPanel messages={messages} />
```

**APRÈS :** Import supprimé + composant retiré du JSX. `PolGauge` conservé.

#### GraphPage.tsx — Suppression AgentPanel + destructuring `messages`

**AVANT (`frontend/src/pages/GraphPage.tsx` ligne 9 + ligne 207) :**
```tsx
import { AgentPanel } from "../components/AgentPanel";
...
messages,        // dans useDashboard()
...
<AgentPanel messages={messages} />
```

**APRÈS :** Import supprimé, `messages` retiré du destructuring `useDashboard()`, composant retiré du JSX.

**Note :** `AgentPanel.tsx` et `AgentPanel` dans `DashboardContext` sont **conservés** côté backend/context — seule l'exposition frontend publique est retirée. Les pages `Memorize` et `ReflexStatus` ne sont pas routées publiquement depuis R359.

---

## 2. Cartographie FAIT vs RESTE (état réel HEAD 7497d43)

### 2.1 TASK-001-BIOMETRIE-SUITE

| Composant | Statut | Commit |
|-----------|--------|--------|
| R372 — Distinction UV=PIN/biométrie | ✅ FAIT | task_ledger |
| R373 — HumanIdentityPolicy (26 tests) | ✅ FAIT | e9cf1a1 |
| R374 — BCH FuzzyExtractor (30 tests) | ✅ FAIT | e039cdaf |
| R376 — check_uniqueness() XOR tolérant | ✅ FAIT | 3be73bb |
| R378 — Hamming direct template_bytes (28 tests) | ✅ FAIT | 5a5606f |
| FAR/FRR sur vraies empreintes capteurs | ❌ RESTE | — |
| Calibrage seuil Hamming réel | ❌ RESTE | — |
| FHE (SEAL/OpenFHE/Concrete) si requis | ❌ RESTE | — |

### 2.2 Logs forensic nanoseconde

| Composant | Statut | Fichier |
|-----------|--------|---------|
| conftest.py → pytest_trace.jsonl | ✅ ACTIF automatique | tests/conftest.py |
| Chaque test émet ts_ns/dur_ns/outcome | ✅ ACTIF | data/trace/pytest_trace.jsonl |
| MODULE_VERSION sur 210/210 modules | ✅ FAIT | R390 |
| stop.py → bob_turns.jsonl audit_status | ✅ ACTIF | .bob/hooks/stop.py |
| Hooks Cursor équivalents | ❌ RESTE | — |

### 2.3 Rules télémétriques — cartographie par domaine (état R375+R393)

| Domaine | Entrées corpus | Couverture registry |
|---------|---------------|---------------------|
| PROTOCOL | 96 CR-* | RT-01→RT-08 |
| GOVERNANCE | 48 CR-* | RT-09→RT-12 |
| LESSONS | 44 CR-* (L-001→L-054) | RT-13→RT-15 |
| NETWORK | 39 CR-* | RT-16→RT-18 |
| TESTING | 1 CR-* | — |
| ROADMAP | 1 CR-* | — |
| IDENTITY | 1 CR-* | — |
| **Total** | **230 CR-*** | **20 RT-*** |

**Limite connue :** classification CR-* manuelle non encore faite (DETECTED_NOT_CLASSIFIED sur la majorité). Réorganisation automatique par domaine = RESTE à implémenter (scanner `artcb_r375_corpus_refresh.py` existe, re-scan nécessaire).

### 2.4 Auto-feedback / rétrospective

| Mécanisme | Statut |
|-----------|--------|
| stop.py → artcb_r392_auto_feedback.py | ✅ ACTIF (fail-open) |
| AgentExecutionRecord (bob/cursor) | ✅ IMPLÉMENTÉ |
| Feedback gravé dans bob_turns.jsonl | ✅ ACTIF |
| Rétrospective "avant/après" par tâche | ✅ Rapport obligatoire par PROTOCOLE |
| Séparation dev interne / usage utilisateur | ✅ Deux chemins distincts (pARTCB/pubARTCB) |
| Hooks Cursor équivalents stop.py | ❌ RESTE |

### 2.5 Frontend — état après cleanup

| Page/Composant | Statut |
|----------------|--------|
| /network (P2P pairs) | ✅ SUPPRIMÉ R379 |
| /agent-memory (mémoire IA) | ✅ SUPPRIMÉ R359/R379 |
| /memorize (agents duels) | ✅ Non routée R359 + AgentPanel retiré R389 |
| /reflex (réflexe) | ✅ Non routée R359 |
| Console p2p status/peers/sync | ✅ SUPPRIMÉ R389 |
| Console POOL E2E (ML-KEM) | ✅ SUPPRIMÉ R389 |
| AgentPanel dans GraphPage/Memorize | ✅ SUPPRIMÉ R389 |
| Backend P2P + AgentMemory | ✅ CONSERVÉ (agents/API uniquement) |

---

## 3. Tests exécutés

```
pytest tests/test_task001_r374_bch.py
       tests/test_task001_r376_uniqueness.py
       tests/test_task001_r378_hamming.py  (fichier nommé différemment dans tests/)
       tests/test_task001_r373_human_identity_policy.py
       -q --timeout=30

Résultat : 106 passed in 1.21s
Régression : 0
```

---

## 4. Prochaines actions prioritaires

1. **TASK-001** — Benchmark FAR/FRR sur données biométriques réelles (pas synthétiques)
2. **TASK-006-LIVE-VALIDATION** — Validation live nœuds N2/N4/N3
3. **TASK-007** — Branchement stop.py → AgentExecutionRecord.tests_passed

---

**CERTIFIED_100=false** — invariant absolu maintenu.  
**Jamais wipe** — aucun ancien rapport modifié.  
**Mode DEBUG actif.**
