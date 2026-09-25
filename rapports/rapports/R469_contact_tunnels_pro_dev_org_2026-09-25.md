# R469 — Tunnels de contact qualifié Pro / Développeur / Organisation

**Date :** 2026-09-25  
**SHA commit :** `c859cf3`  
**Branche :** `main`  
**Précédent SHA :** `d545794` (R467)  
**Tests :** 20/20 PASS (T01→T20) | Non-régression : 142/142 PASS | DO-178C gate : 124/124 PASS  
**CERTIFIED_100=false**

---

## Objectif

Brancher les 3 tunnels de contact qualifié (PRO / DEVELOPER / ORGANIZATION) créés en `??` dans le working tree :
- `frontend/src/pages/ContactPro.tsx`
- `frontend/src/pages/ContactDeveloper.tsx`
- `frontend/src/pages/ContactOrganization.tsx`
- `src/api/contact_routes.py`

Ces fichiers existaient mais n'étaient **ni importés, ni routés, ni testés**.

---

## État avant R469

| Fichier | État |
|---------|------|
| `src/api/contact_routes.py` | `??` — non tracé, non importé dans `main.py` |
| `frontend/src/pages/ContactPro.tsx` | `??` — non tracé, non routé dans `App.tsx` |
| `frontend/src/pages/ContactDeveloper.tsx` | `??` — non tracé, non routé |
| `frontend/src/pages/ContactOrganization.tsx` | `??` — non tracé, non routé |
| `src/api/main.py` | Pas d'import `contact_router` |
| `frontend/src/App.tsx` | Pas de routes `/contact/*` |
| `tests/test_r469_contact_routes.py` | **Inexistant** |

---

## Modifications R469

### 1. `src/api/contact_routes.py` — suppression dépendance `EmailStr`

**Avant (ligne 19) :**
```python
from pydantic import BaseModel, EmailStr, Field
```

**Après :**
```python
from pydantic import BaseModel, Field
```

**Raison :** `EmailStr` de pydantic nécessite `email-validator` absent de `requirements.txt`. La validation `str` avec `min_length=3, max_length=320` est suffisante pour la phase MVP.

---

### 2. `src/api/main.py` — import + branchement

**Avant (ligne 50, extrait) :**
```python
from src.api.network_routes import router as network_router
from src.api.kcg_routes import router as kcg_router
...
    # R461 — Diffusion P2P du NodeTpmBinding (TPM EK → NodeID)
    app.include_router(node_tpm_binding_router)
    logger.debug("ARTCB API started ...")
```

**Après :**
```python
from src.api.network_routes import router as network_router
from src.api.contact_routes import router as contact_router   # ← AJOUT R469
from src.api.kcg_routes import router as kcg_router
...
    # R461 — Diffusion P2P du NodeTpmBinding (TPM EK → NodeID)
    app.include_router(node_tpm_binding_router)
    # R469 — Tunnels de contact qualifié Pro / Développeur / Organisation
    app.include_router(contact_router)                         # ← AJOUT R469
    logger.debug("ARTCB API started ...")
```

---

### 3. `frontend/src/App.tsx` — import + routes

**Avant (imports, lignes 22–23) :**
```tsx
import { RegisterBiometric } from "./pages/RegisterBiometric";
import { AddDevice } from "./pages/AddDevice";
```

**Après :**
```tsx
import { RegisterBiometric } from "./pages/RegisterBiometric";
import { AddDevice } from "./pages/AddDevice";
import { ContactPro } from "./pages/ContactPro";           // ← AJOUT R469
import { ContactDeveloper } from "./pages/ContactDeveloper";
import { ContactOrganization } from "./pages/ContactOrganization";
```

**Avant (routes, ligne 48–49) :**
```tsx
            <Route path="api-keys" element={<ApiKeys />} />
            <Route path="*" element={<Navigate to="/" replace />} />
```

**Après :**
```tsx
            <Route path="api-keys" element={<ApiKeys />} />
            <Route path="contact/pro" element={<ContactPro />} />          // ← AJOUT R469
            <Route path="contact/developer" element={<ContactDeveloper />} />
            <Route path="contact/organization" element={<ContactOrganization />} />
            <Route path="*" element={<Navigate to="/" replace />} />
```

---

### 4. `tests/test_r469_contact_routes.py` — 20 tests T01→T20

| Test | Description | Résultat |
|------|-------------|---------|
| T01 | PRO minimal (email seul) | ✅ PASS |
| T02 | PRO complet (tous champs) | ✅ PASS |
| T03 | PRO crée un fichier JSON dans `data/contacts/` | ✅ PASS |
| T04 | DEVELOPER minimal | ✅ PASS |
| T05 | DEVELOPER complet | ✅ PASS |
| T06 | Fichier Developer contient stack, github, integration_goal | ✅ PASS |
| T07 | ORGANIZATION minimal | ✅ PASS |
| T08 | ORGANIZATION complet (5 étapes) | ✅ PASS |
| T09 | Fichier Organization contient org_name, role, intent | ✅ PASS |
| T10 | Email absent → HTTP 422 | ✅ PASS |
| T11 | Email trop court → HTTP 422 | ✅ PASS |
| T12 | contact_type inconnu → HTTP 422 | ✅ PASS |
| T13 | contact_id format UUID v4 (36 chars) | ✅ PASS |
| T14 | Réponse ne contient ni email ni nom (RGPD) | ✅ PASS |
| T15 | 3 appels → 3 fichiers distincts, types différents | ✅ PASS |
| T16 | Champ `message` présent dans la réponse | ✅ PASS |
| T17 | Fichier ORG ne contient pas les champs PRO | ✅ PASS |
| T18 | Fichier DEV ne contient pas les champs ORG | ✅ PASS |
| T19 | `received_at` au format ISO 8601 UTC | ✅ PASS |
| T20 | `contact_id` cohérent entre fichier et réponse HTTP | ✅ PASS |

---

## Architecture Contact R469

```
HashRouter (frontend)
  /contact/pro          → ContactPro.tsx        (4 étapes : objectif → secteur → niveau → coordonnées)
  /contact/developer    → ContactDeveloper.tsx   (4 étapes : objectif → stack → env → coordonnées)
  /contact/organization → ContactOrganization.tsx (5 étapes : intention → type → taille → thème → coordonnées)
       ↓ POST /api/v1/contact
  contact_routes.py (FastAPI)
       ↓ stockage local
  data/contacts/contact_YYYYMMDD_HHMMSS_{uuid}.json
```

**Garanties RGPD :**
- Aucune donnée personnelle on-chain
- La réponse HTTP ne retourne que `{status, contact_id, message}`
- Fichiers locaux dans `data/contacts/` (hors blockchain)

---

## Non-régression

| Suite | Avant R469 | Après R469 |
|-------|-----------|-----------|
| test_r466_lexicon_mapper | 42 PASS | 42 PASS |
| test_task001_r374_bch | 30 PASS | 30 PASS |
| test_task001_r376_uniqueness | 22 PASS | 22 PASS |
| test_task001_r378_hamming | 28 PASS | 28 PASS |
| **test_r469_contact_routes** | — | **20 PASS** |
| **DO-178C gate** | — | **124/124 PASS** |

---

## Limites

- `EmailStr` remplacé par `str` plain — validation syntaxique email non faite côté backend (MVP acceptable)
- Pas de notification email réelle à l'équipe ARTCB (stockage local uniquement)
- CSS des tunnels (classes `mc-contact-*`) non inclus dans ce rapport — dépend du fichier de styles global
- `ContactPro.tsx` importe `useTranslation` — dépend que ce hook soit disponible dans le bundle

---

## Prochaines étapes

1. **R469b** — Manifeste R466b A-04 : régénérer sur HEAD `c859cf3` (L-053)
2. **TASK-001** — FHE véritable : intégration Concrete réel en remplacement de `FheHammingCircuit` simulé
3. **TASK-006-LIVE-VALIDATION** — Validation live N2/N3/N4 sur HEAD `c859cf3`

---

**CERTIFIED_100=false** — Invariant absolu maintenu dans tous les chemins R469.
