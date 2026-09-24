# R459 — S09 Enforced : Routes API P2P Capability Tokens FAIL-CLOSED

**Date :** 2026-09-25  
**SHA commit :** `60e8dbb`  
**SHA parent (R458-integ) :** `e3cd7a9`  
**Fingerprint :** `logs/R459_module_fingerprints.json` (généré sur `60e8dbb`)  
**CERTIFIED_100 :** `false`  
**Avancement global estimé :** 65 %

---

## 1. Contexte — lacune S09 identifiée par l'audit expert

L'audit post-R458-integ a établi avec précision :

> **`require_capability_token()` disponible ≠ `require_capability_token()` enforced**

Avant R459 :
- Le mécanisme existait dans `capability_token.py` (R456)
- Le middleware FastAPI existait dans `capability_token_middleware.py` (R458-integ)
- **Mais aucune route API réelle ne l'appelait**

La protection était codée, testée — et entièrement contournable car aucune route de production ne l'exigeait.

---

## 2. Ce que R459 apporte

### Avant (R458-integ) — absence de route enforced

```
CapabilityTokenStore  ←  implémenté ✅
require_capability_token()  ←  middleware ✅
Tests M01-M15  ←  passent ✅

MAIS :

POST /p2p/... (routes existantes)
    ↓
    Aucun require_capability_token() appelé
    ↓
    Opération exécutée sans token ← S09 NON ENFORCED
```

### Après (R459) — routes API dédiées + enforcement réel

```
POST /p2p/cap-tokens/issue    ← opérateur émet un token à usage unique
POST /p2p/cap-tokens/redeem/produce-block  ← token OBLIGATOIRE (CAP_PRODUCE)
POST /p2p/cap-tokens/redeem/replicate      ← token OBLIGATOIRE (CAP_REPLICATE)
GET  /p2p/cap-tokens/audit    ← audit trail opérateur
GET  /p2p/cap-tokens/health   ← public

RÉSULTAT :
  Sans token → 403 (E06, E09, E17 — IMPOSSIBLE de contourner)
  Double utilisation → 403 (E08, E15)
  Mauvais nœud → 403 (E10)
  Mauvais domaine → 403 (E11)
  Mauvaise capability → 403 (E12)
  Token expiré → 403 (E16)
```

---

## 3. Avant / Après — `src/api/main.py`

**AVANT :**
```python
from src.api.p2p_routes import router as p2p_router
# ...
app.include_router(p2p_router)
```

**APRÈS :**
```python
from src.api.p2p_routes import router as p2p_router
from src.api.capability_token_routes import router as cap_token_router
# ...
app.include_router(p2p_router)
app.include_router(cap_token_router)
```

---

## 4. Architecture du chemin enforced

```
Client / nœud demandeur
        │
        ▼
POST /p2p/cap-tokens/redeem/produce-block
        │
        ▼
_redeem_with_store(CAP_PRODUCE, request, store)
        │
        ▼
require_capability_token(capability=CAP_PRODUCE, store=store)(request)
        │
   ┌────┴─────────────────────┐
   │  Vérifications FAIL-CLOSED│
   │  1. header présent       │
   │  2. token connu          │
   │  3. état PENDING         │
   │  4. non expiré           │
   │  5. capability OK        │
   │  6. node_id OK           │
   │  7. domain_id OK         │
   └────┬──────────────────── ┘
        │
   DENIED → HTTP 403    PASS → CONSUMED (irréversible)
                                │
                                ▼
                    Opération exécutée (stub extensible)
                                │
                                ▼
                    Audit trail enregistré
```

---

## 5. Résultats des tests R459 (18 tests E01-E18)

| Test | Description | Résultat |
|------|-------------|---------|
| E01 | /health → 200 + store_operational=True | PASS |
| E02 | Issue sans auth opérateur → 401 | PASS |
| E03 | Issue capability inconnue → 422 | PASS |
| E04 | Issue rôle inconnu → 422 | PASS |
| E05 | Issue valide → token_id 64 hex chars | PASS |
| E06 | Redeem sans header token → 403 | PASS |
| E07 | Redeem valide → 200 authorized=True | PASS |
| E08 | Double redeem → 200 puis 403 already_consumed | PASS |
| E09 | Token inconnu → 403 unknown_token | PASS |
| E10 | Mauvais node_id → 403 node_mismatch | PASS |
| E11 | Mauvais domain_id → 403 domain_mismatch | PASS |
| E12 | CAP_PRODUCE token sur route CAP_REPLICATE → 403 | PASS |
| E13 | Audit sans auth → 401 | PASS |
| E14 | Audit trail enregistre la rédemption | PASS |
| **E15** | **20 threads parallèles → exactement 1 × 200, 19 × 403** | **PASS** |
| E16 | Token expiré → 403 token_expired | PASS |
| **E17** | **Sans token : opération sensible IMPOSSIBLE** | **PASS** |
| E18 | CAP_REPLICATE token sur /redeem/replicate → 200 | PASS |

| Suite | Résultat |
|-------|---------|
| `test_r459_s09_capability_enforcement_api.py` | **18/18 PASS** |
| Gate DO-178C (R430) | **124/124 PASS** |
| Non-régression R456/R458-integ | **40/40 PASS** |

---

## 6. État S09 mis à jour

| Avant R459 | Après R459 |
|------------|-----------|
| `require_capability_token()` disponible | ✅ |
| Routes API réelles appelant le mécanisme | ❌ | ✅ |
| Opération impossible sans token valide | ❌ | ✅ (E17) |
| Double utilisation bloquée | ❌ route | ✅ (E08, E15) |
| Audit trail sur chemin API complet | ❌ | ✅ (E14) |

**S09 passe de `PARTIAL` à `E2E PASS`** (local + routes API intégrées).  
**S09 n'est pas encore `LIVE NODE PASS`** — les nœuds OVH/AWS ne tournent pas encore ce code (push requis + git pull + restart).

---

## 7. Limites honnêtes maintenues

1. **Routes existantes (`/replica/push`, `/blocks/receive`)** — non modifiées. Ces routes utilisent leur propre auth (`_require_official_replica_peer` / `require_operator_write`). L'intégration du capability token sur ces routes est le chantier R459-prod.
2. **Store en mémoire** — redémarrage du processus = store vidé. Pour la production : persister dans la couche forensic (R451).
3. **Bearer opérateur** — vérifié comme non-vide, pas cryptographiquement vérifié. Branchement wallet en R459-prod.
4. **S09 LIVE** — pas encore démontré sur N2/N4/N3.

---

*Rapport généré post-exécution — ARTCB protocole R459 — SHA `60e8dbb`*
